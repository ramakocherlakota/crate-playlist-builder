# Crate Playlist Builder

Browse your Apple Music library as a collapsible **Artist → Album → Song** tree, tick what you want, and build a playlist from it.

Live at **https://crate.ramakocherlakota.net**

## How it works

1. In Music on a Mac: **File → Library → Export Library…** and save the XML.
2. Load it on the page (or drag it on). Everything runs in your browser; nothing is uploaded. The library, your edits and your view (search, toggles, open folders) are remembered in this browser (IndexedDB and localStorage) until you choose **Forget this library**.
3. Tick artists, albums or songs. Open any number of existing playlists (or start new ones) and switch between them; each keeps its own changes. Press ♪ next to a song to hear Apple's 30-second preview (looked up through the public iTunes Search API).
4. Copy, download or share (AirDrop from a phone) the generated AppleScript and run it in Script Editor on your Mac. One script covers every playlist you changed. It finds each song by its persistent ID, so it works for streaming Apple Music songs as well as local files.

### Changes, not rewrites

The script applies only what you changed: unticked songs are removed, newly ticked songs are added at the end (existing order is kept), and a renamed playlist is renamed in Music. Anything already done is skipped, so scripts made on different devices can be run in any order, and running one twice is harmless. **Undo** (or ⌘Z) reverses the last change: ticks, renames, closing a playlist or Mark as applied. Loading a newer library (or refreshing from Spotify) keeps your unapplied edits on top of any changes made elsewhere. **Show changes** lists exactly which songs each playlist will gain or lose (with a per-song Undo). After exporting a script, **Mark as applied** resets the change counts so the next script only carries newer edits.

## Spotify

Switch the page to **Spotify** (top right) to curate Spotify playlists instead. Crate signs in with Spotify's PKCE flow straight from the browser (no server, no client secret) and builds the same Artist → Album → Song tree from your Liked Songs, saved albums and the songs in playlists you own or collaborate on. That library is cached in the browser; **Refresh from Spotify** reloads it. Editing works the same (several playlists at once, Show changes, Undo), and **Apply to Spotify** sends the changes directly: unticked songs are removed, new ones appended, renames applied and new playlists created (private). Requests are paced to respect Spotify's rate limits, and a spent development-mode quota is reported plainly.

Each service keeps its own library and edits in the browser; switching reloads the page.

Spotify setup: a Spotify developer app with redirect URI `https://crate.ramakocherlakota.net/` and the Web API enabled (the client ID is in [`site/spotify.js`](site/spotify.js)). Since February 2026 Spotify requires the app owner to have Premium, and development-mode apps are limited to 5 users, each added under User Management.

The app is [`site/index.html`](site/index.html) plus [`site/spotify.js`](site/spotify.js).

## Hosting

`infra/site.yml` is a CloudFormation stack that creates:

- a private S3 bucket
- a CloudFront distribution (HTTPS, reads the bucket through Origin Access Control)
- an ACM certificate for `crate.ramakocherlakota.net`, validated automatically through Route 53
- Route 53 A/AAAA alias records pointing at CloudFront
- an IAM role that GitHub Actions on `main` assumes via OIDC (no stored AWS keys)

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

### Deploys

Every push to `main` that touches `site/` runs `.github/workflows/deploy.yml`, which syncs `site/` to the bucket and invalidates the CloudFront cache. You can also run it by hand from the Actions tab.
