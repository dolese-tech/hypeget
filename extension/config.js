// Build flavour. tools/build_extension.py rewrites this file in the packages it makes:
// store packages set store: true, which hides in-page video download on sites whose
// store policies forbid it (YouTube). The app itself can still handle those links.
var HYPERGET_BUILD = { store: false, version: "0.1.0" };

function hypergetRestricted(url) {
  if (!HYPERGET_BUILD.store) return false;
  try {
    return /(^|\.)(youtube\.com|youtube-nocookie\.com|youtu\.be|googlevideo\.com)$/i.test(new URL(url).hostname);
  } catch (e) {
    return false;
  }
}
