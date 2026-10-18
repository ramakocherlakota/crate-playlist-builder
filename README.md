# Crate Playlist Builder

Browse your Apple Music library as a collapsible **Artist → Album → Song** tree, tick what you want, and build a playlist from it.

Live at **https://crate.ramakocherlakota.net**

## How it works

1. In Music on a Mac: **File → Library → Export Library…** and save the XML.
2. Load it on the page (or drag it on). Everything runs in your browser; nothing is uploaded.
3. Tick artists, albums or songs, or start from an existing playlist.
4. Copy or download the generated AppleScript and run it in Script Editor. It finds each song by its persistent ID, so it works for streaming Apple Music songs as well as local files.

The whole app is one static file: [`site/index.html`](site/index.html).

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
