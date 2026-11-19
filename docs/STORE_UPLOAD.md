# Publishing the extension, the IDM way

Goal: users install HyperGet, open Chrome or Edge, see **"New extension added"** and
click **Enable**. That only works for extensions published in the stores, so publish
first, then put the store IDs into the installer and website.

Everything to paste or upload is in `extension/store/` (texts in `listing.md`).

## 0. Before you start

- [ ] **A working installer.** Reviewers need HyperGet installed to try the extension.
      Get the GitHub Actions Windows build running and publish a release first
      (push a tag such as `v0.1.0`), so https://hyperget.dolese.tech/download works.
- [ ] Build the package: `python tools/build_extension.py` and use
      `dist/extension/hyperget-extension-0.1.0-store.zip` (also attached to each
      GitHub build).

## 1. Chrome Web Store

1. Create the developer account at https://chrome.google.com/webstore/devconsole
   with a Dolese Tech Google account and pay the one-time **US$5** fee.
   Verify the contact email (use support@dolese.tech or the account email).
2. **New item → upload** the `-store.zip`.
3. **Store listing** tab: description, category, language, icon, screenshots, promo
   tiles, website and support links from `listing.md`.
4. **Privacy practices** tab: single purpose, permission justifications, remote code
   "No", data usage, privacy policy URL, all from `listing.md`.
5. **Distribution**: Public, all regions.
6. **Submit for review.** First reviews usually take a few days, longer for
   extensions with broad host permissions.
7. When it's published, copy the **item ID** (32 letters, in the store URL).

## 2. Microsoft Edge Add-ons

1. Register at https://partner.microsoft.com/dashboard/microsoftedge (free) with a
   Dolese Tech Microsoft account.
2. **Create new extension → upload** the same `-store.zip`.
3. Availability: Public, all markets.
4. Properties: category Productivity, privacy policy URL, website, support email.
5. Store listings (English): description, short description, search terms, logo,
   screenshots, promo tiles from `listing.md`.
6. Notes for certification from `listing.md`, then **Publish**.
7. When it's live, copy the **product ID** from the store URL
   (`microsoftedge.microsoft.com/addons/detail/<id>`).

## 3. Turn on automatic install (installer)

In GitHub: **Settings → Secrets and variables → Actions → Variables → New repository variable**

| Name | Value |
|---|---|
| `HYPERGET_CHROME_EXTENSION_ID` | the Chrome item ID |
| `HYPERGET_EDGE_EXTENSION_ID` | the Edge product ID |

The next Windows build uses them twice:

- **Install prompt**: registry entries (`HKCU\Software\Google\Chrome\Extensions\<id>`
  and `HKCU\Software\Microsoft\Edge\Extensions\<id>`, see `packaging/installer.iss`) so
  the browsers offer the extension after installing HyperGet.
- **Native messaging**: the IDs are written to `hypeget/store_ids.json` inside the app,
  so HyperGet's browser helper (`tech.dolese.hyperget`) accepts the store versions.
  Without this step the store extension shows "Not installed" even with HyperGet
  installed. The unpacked extension that ships with HyperGet always works: its ID is
  pinned by the `key` in `extension/manifest.json`.

Uninstalling HyperGet removes the entries and the helper registration.

## 4. Point the website at the stores

In `website/site.js`, fill in:

```js
const STORE = { chrome: "<chrome item id>", edge: "<edge product id>" };
```

Push and redeploy: every "Add to Chrome" button then opens the store, and the
download page shows **Add to Chrome / Add to Edge** instead of the manual steps.

## Store version vs. full version

| | Store zip | Full zip (inside the HyperGet download) |
|---|---|---|
| Download button on videos | Every site except YouTube | Every site |
| YouTube | Paste the link into HyperGet's Add URL | Button works |
| Everything else | Same | Same |

The Chrome Web Store doesn't accept extensions that download YouTube videos, so the
store build hides the in-page button there (`extension/config.js`). The app itself
still downloads YouTube links pasted into it.

## The extension signing key

`hyperget-extension-key.pem` (given to you separately, **not** in the repo) is the
private half of the `key` in `extension/manifest.json`. It fixes the unpacked
extension's ID (`oeclpagllkokmfmdpapcaeljjcbndgao`). Keep it safe, for example in a
password manager. It's needed only to package the extension as a signed `.crx` outside
the stores. Never commit it: anyone with it could make an extension with the same ID.

## Updating later

Raise `version` in `extension/manifest.json`, run `python tools/build_extension.py`,
upload the new `-store.zip` to both dashboards. Browsers update automatically.
