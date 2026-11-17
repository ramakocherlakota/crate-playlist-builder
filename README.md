# Crate Playlist Builder

Browse your Apple Music library as a collapsible **Artist → Album → Song** tree, tick what you want, and build a playlist from it.

Live at **https://crate.ramakocherlakota.net**

## How it works

The screen is a playlist list on the left and the open playlist on the right: rename it in place, search or filter the tree (**All songs / In playlist / Changes**), and tick songs. Along the top:

- the **library chip** (song count and date) opens a menu for loading a newer library file, won't-sync warnings and forgetting the library;
- **Undo** reverses the last change;
- **Help** has the instructions, including setting up the shortcut.

Above the tree, **View** holds grouping (by album artist), album order (A–Z or by year), ignoring sort names, and expand/collapse all. Menus keep themselves on screen on narrow phones. **Review & apply** (enabled once something has changed) shows every change and the ways to apply it on this device.

On a phone the playlist list and the playlist being edited are separate screens (with a back button), and a bar at the bottom shows the change count and Review & apply. Tapping the count opens a sheet listing the changes, each with Undo.

1. In Music on a Mac: **File → Library → Export Library…** and save the XML.
2. Load it on the page (or drag it on). Everything runs in your browser; nothing is uploaded. The library, your edits and your view settings are remembered in this browser (IndexedDB and localStorage) until you choose **Forget this library**.
3. Tick artists, albums or songs. Open any number of existing playlists (or start new ones) and switch between them; each keeps its own changes. Press ♪ next to a song to hear Apple's 30-second preview (looked up through the public iTunes Search API).
4. Apply the changes, either:
   - on the Mac, with a generated AppleScript run in Script Editor. Copy or download it, or on an iPhone/iPad use **Share script** (the main button there) to AirDrop it to the Mac. One script covers every playlist you changed. It finds each song by its persistent ID, so it works for streaming Apple Music songs as well as local files.
   - on the phone, with **Add with Shortcuts** (additions only; see below).

### Songs that aren't in the library file yet

A song bought or added after the export (say, bought on the phone) can be added by hand. Use **Add a song that isn't here…** in the library menu, or the link that appears when a search finds nothing. It searches Apple's catalog through the iTunes Search API, the same lookup the previews use (via the site's `/search`; see Hosting), or takes a typed title, artist and album. The song goes into the tree marked **hand-added** (✎ on a phone) and is ticked in the open playlist.

Hand-added songs are kept separately from the library, under the IndexedDB key `extras`, with a made-up persistent ID (`itunes:<trackId>` or `hand:<random>`), so they survive loading a new library file. Because they have no real persistent ID:

- the Mac script finds them by title, artist and album (`addSongs` / `removeSongs` in `applyChanges`);
- the shortcut already finds every song that way.

When a loaded library file has a song with the same title, artist and album (ignoring capitals), Crate switches to that copy, moves your ticks over and drops the hand-added one. The **Add a song** panel lists hand-added songs, each with a **Remove** button.

To use Crate like an app on the phone, use Safari's Share → **Add to Home Screen**: the page supplies the icon and the name "Crate". It deliberately doesn't run as a full-screen web app, because that would have its own storage, separate from Safari's, and the return from Shortcuts always opens in Safari.

### Changes, not rewrites

The script applies only what you changed:

- unticked songs are removed;
- newly ticked songs are added at the end, keeping the existing order;
- a renamed playlist is renamed in Music.

Anything already done is skipped, so scripts made on different devices can be run in any order, and running one twice is harmless.

- **Undo** (or ⌘Z) reverses the last change: ticks, renames, closing a playlist or Mark as applied.
- Loading a newer library keeps your unapplied edits on top of any changes made elsewhere.
- **Review & apply** lists exactly which songs each playlist will gain or lose, with a per-song Undo.
- The tree's **Changes** filter highlights those songs in place.
- After exporting a script, **Mark as applied** resets the change counts, so the next script only carries newer edits.

### One live tab

Only one Crate tab is live at a time. Returning from Shortcuts opens a new Safari tab: iOS gives no way to reuse the old one, and a page can't close tabs it didn't open. Two tabs editing at once would also overwrite each other's saved edits.

So each tab announces itself over a `BroadcastChannel` when it's opened or used. Any other Crate tab then:

1. saves its pending edit;
2. stops saving;
3. shows **Crate continued in another tab**, with a **Use this tab** button that reloads it with the latest edits.

### Keeping the phone in sync

With **Afterwards, save an updated Library.xml to iCloud Drive › Crate** ticked (the default), each script finishes by writing the library (songs and playlists) to `iCloud Drive/Crate/Library.xml`. It uses the same format as Music's own export, since Music has no scriptable Export Library. Load that file in Crate on the phone: what the script applied shows as done, and edits not yet run stay pending.

The playlists themselves reach the phone's Music app:

- automatically, through **Sync Library** (Apple Music or iTunes Match);
- or, without a subscription, by syncing the iPhone with the Mac in Finder (by cable, or over Wi-Fi once **Show this iPhone when on Wi-Fi** is ticked).

The export also records each song's iCloud status. Crate marks songs iCloud won't store (duplicate, ineligible and so on) with **won't sync**. It warns in the library menu, the playlist list and Review & apply when a playlist contains one, because such a playlist won't reach your other devices.

### Adding songs from the phone with Shortcuts

**Add with Shortcuts** runs a shortcut you install once, `Crate Add Songs`, on the device itself. One run covers every playlist with additions. With Sync Library on, iCloud carries the changes to the Mac.

Shortcuts can't remove songs or rename playlists, so only additions are sent, using the playlist's current name in Music. Removals and renames stay pending for the Mac script, or for doing by hand in Music. The button is disabled when there's nothing to add.

**What Crate sends:** JSON with:

- `v`, the version Crate needs;
- `need_v2` … `need_vN` markers for that version;
- a flat `songs` list. Each song has `index`, `playlist`, `title`, `artist` and `album`, plus `create` on the first song of a playlist that doesn't exist yet.

**What the shortcut (version 4) does:**

1. Stops before adding anything if `need_v5` is present, reporting `v4 outdated`. This is a presence test because Shortcuts won't compare dictionary values.
2. For each song:
   1. Creates the playlist if asked, then waits 3 seconds, since a brand-new playlist can't be found by name straight away.
   2. Finds the song with Find Music, by exact title, artist and album.
   3. If that fails, looks at every song with that title and takes one whose artist and album match ignoring capitals. The phone can capitalise an album differently from the Mac's export, and requiring both keeps it from picking a live or other version.
   4. Adds the song to its playlist.
3. Returns `v4 missing:<indexes>` to Crate through the x-callback URL.

**Back in Crate:** the found songs are marked as added, and the ones not found stay pending. The message shows the artist and album Crate searched for. If the shortcut reports an older version, stops itself as outdated, or stops with an error, Crate links to the current version.

**Installing:**

- **iCloud link:** the easiest install, linked from the app's Help and the guide. The link is a snapshot of one version.
- **Setup guide:** a walkthrough at [`site/shortcut-setup.html`](site/shortcut-setup.html) (https://crate.ramakocherlakota.net/shortcut-setup.html), with steps for building the shortcut by hand. A short version is in the app's Help.
- **Signed file:** a ready-made `site/crate-add-songs-unsigned.shortcut`, generated by [`tools/make_shortcut.py`](tools/make_shortcut.py). Sign it on a Mac with `shortcuts sign --mode anyone --input crate-add-songs-unsigned.shortcut --output "Crate Add Songs.shortcut"` and double-click the result to import it.

**Releasing a new shortcut version:**

1. Bump `VERSION` in `tools/make_shortcut.py` and `SHORTCUT_VERSION` in `site/index.html` together.
2. Regenerate the file: `cd site && python3 ../tools/make_shortcut.py`.
3. Update the version text in the guide's steps and the app's Help.
4. Install, test and share the new version from Shortcuts. Put its new iCloud link in `SHORTCUT_INSTALL_URL` and the Help in `site/index.html`, and in `site/shortcut-setup.html`.

## Files

- [`site/index.html`](site/index.html): the whole app (HTML, CSS and JavaScript in one file).
- [`site/shortcut-setup.html`](site/shortcut-setup.html): the Shortcuts setup guide.
- `site/crate-add-songs-unsigned.shortcut`: the generated, unsigned shortcut.
- `site/icon.svg`, `site/apple-touch-icon.png`: the icons.
- [`tools/make_shortcut.py`](tools/make_shortcut.py): builds the shortcut file.
- [`infra/site.yml`](infra/site.yml) and [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml): hosting and deployment (below).

## Hosting

`infra/site.yml` is a CloudFormation stack that creates:

- a private S3 bucket
- a CloudFront distribution (HTTPS, reads the bucket through Origin Access Control)
- an ACM certificate for `crate.ramakocherlakota.net`, validated automatically through Route 53
- Route 53 A/AAAA alias records pointing at CloudFront
- a second CloudFront origin and cache behaviour that pass `/search` on to Apple's catalog search
- an IAM role that GitHub Actions on `main` assumes via OIDC (no stored AWS keys)

The distribution also forwards `/search` to Apple's catalog search (`itunes.apple.com/search`), caching results for a day. iPhones are turned away when they ask Apple directly, so Crate's song previews and **Add a song** ask `/search` on Crate's own site first, falling back to asking Apple directly where that isn't set up.

### One-time setup

```sh
# Find the hosted zone ID for ramakocherlakota.net
aws route53 list-hosted-zones-by-name --dns-name ramakocherlakota.net \
  --query 'HostedZones[0].Id' --output text      # -> /hostedzone/Z123... (use the Z123... part)

# Create the stack (must be us-east-1). Takes ~5-15 minutes while the cert validates
# and CloudFront deploys. If your account already has the GitHub OIDC provider,
# add CreateOidcProvider=false.
aws cloudformation deploy --region us-east-1 \
  --stack-name crate-playlist-builder \
  --template-file infra/site.yml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides HostedZoneId=Z123...

# Read the outputs
aws cloudformation describe-stacks --region us-east-1 --stack-name crate-playlist-builder \
  --query 'Stacks[0].Outputs' --output table
```

Then set three **repository variables** (Settings → Secrets and variables → Actions → Variables), or with the GitHub CLI:

```sh
gh variable set AWS_ROLE_ARN --body "<DeployRoleArn>"
gh variable set S3_BUCKET --body "<BucketName>"
gh variable set CLOUDFRONT_DISTRIBUTION_ID --body "<DistributionId>"
```

To change the stack later (for example, after editing `infra/site.yml`), run the same `aws cloudformation deploy` command. `HostedZoneId` and any other parameters you set before keep their values, so you can leave out `--parameter-overrides`. GitHub's deploys only update the files in the bucket, not the stack.

### Deploys

Every push to `main` that touches `site/` runs `.github/workflows/deploy.yml`, which syncs `site/` to the bucket and invalidates the CloudFront cache. You can also run it by hand from the Actions tab.
