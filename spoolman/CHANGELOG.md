# Changelog



## 0.27.1

Many fixes and some new features!

If your standalone install refused to start after updating to v0.27.0, this fixes it. It was being installed on Python 3.15, which one of our dependencies doesn't support yet, and updating moves it back to Python 3.14.

A spool tare of 0 is now kept as 0 instead of falling back to the filament or manufacturer's empty spool weight. If you have spools with a tare of 0 that relied on that fallback, check their remaining weight after updating.

## Highlights
* Added filament and manufacturer lists, this was highly requested in the new client, hope it fits the needs!
* OpenPrintTag tags can now be decoded. `/tag/scan` with format `openprinttag` returns what's on the tag, and can create the manufacturer, filament and spool for a tag it doesn't know yet (#1112 by @goeland86, with help from @Ricky1966).
* The QR scanner lets you pick which camera to use (#1184 by @IdefixRC).
* Tags read by the phone's own NFC now open the matching spool or filament.
* The library has a Show lot numbers toggle and remembers its page size.
* Slovenian and Korean are now in the language picker.

## Notable fixes
* Typing in an inspector field no longer drops characters while it autosaves (#1307).
* The Manufacturer filter no longer gets stuck on Loading when two manufacturers share a name (#1306).
* Nightly backups work on network shares again, and a backup can no longer hang.
* A typed 0 is kept for tare, price, temperatures and low-stock thresholds.
* `/metrics` no longer exports archived and deleted spools.
* Importing from SpoolmanDB reuses an existing manufacturer with the same name instead of creating a duplicate.
* Locations with a slash in their name can be renamed.
* Scanning an OpenPrintTag tag without an instance UUID no longer fails on Python 3.10 and 3.11.

## Full change list
* Speed up armv7 image builds when the layer cache misses by @Donkie in https://github.com/Donkie/Spoolman/pull/1186
* Add update available indicator by @Donkie in https://github.com/Donkie/Spoolman/pull/1193
* Resolve label fields in custom QR URL templates by @Donkie in https://github.com/Donkie/Spoolman/pull/1194
* Let the QR scanner pick between cameras by @IdefixRC in https://github.com/Donkie/Spoolman/pull/1184
* Auto-navigate on tags read by the phone's own NFC by @Donkie in https://github.com/Donkie/Spoolman/pull/1187
* Filament and manufacturer lists in the Library by @Donkie in https://github.com/Donkie/Spoolman/pull/1248
* Keep an explicit 0 tare when measuring a spool by @Donkie in https://github.com/Donkie/Spoolman/pull/1253
* Stop exporting archived and deleted spools in /metrics by @Donkie in https://github.com/Donkie/Spoolman/pull/1254
* Probe data dir writability with a uniquely named temp file by @Donkie in https://github.com/Donkie/Spoolman/pull/1255
* Fix nightly backups failing on network shares, and the backup hang by @Donkie in https://github.com/Donkie/Spoolman/pull/1256
* Open deep-linked items the list hasn't loaded by @Donkie in https://github.com/Donkie/Spoolman/pull/1257
* Keep a stored threshold of 0 across reloads by @Donkie in https://github.com/Donkie/Spoolman/pull/1258
* Let dashboard cards use the screen height by @Donkie in https://github.com/Donkie/Spoolman/pull/1260
* Offer empty dashboard locations in the location pickers by @Donkie in https://github.com/Donkie/Spoolman/pull/1262
* Wait for page data before taking Argos screenshots by @Donkie in https://github.com/Donkie/Spoolman/pull/1263
* Decode inverted QR codes in client_v2 scanner on Firefox by @Donkie in https://github.com/Donkie/Spoolman/pull/1195
* Page through filament spools and dashboard groups by @Donkie in https://github.com/Donkie/Spoolman/pull/1259
* Run CI on bot PRs and merge Weblate PRs weekly by @Donkie in https://github.com/Donkie/Spoolman/pull/1264
* Keep a typed 0 for tare, price and temperatures by @Donkie in https://github.com/Donkie/Spoolman/pull/1265
* Allow renaming a location whose name contains a slash by @Donkie in https://github.com/Donkie/Spoolman/pull/1267
* Mention filaments in the unknown-tag and any-reader texts by @Donkie in https://github.com/Donkie/Spoolman/pull/1268
* Bump dependencies within their declared ranges by @Donkie in https://github.com/Donkie/Spoolman/pull/1269
* Reuse a same-name manufacturer when importing from SpoolmanDB by @Donkie in https://github.com/Donkie/Spoolman/pull/1266
* Page the filament picker when printing labels by @Donkie in https://github.com/Donkie/Spoolman/pull/1275
* Add a Show lot numbers toggle to the library by @Donkie in https://github.com/Donkie/Spoolman/pull/1274
* Drop the unused influxdb-client dependency by @Donkie in https://github.com/Donkie/Spoolman/pull/1272
* Offer Slovenian and Korean in the language picker by @Donkie in https://github.com/Donkie/Spoolman/pull/1279
* Make websocket subscriber cleanup idempotent by @dajiaohuang in https://github.com/Donkie/Spoolman/pull/1216
* Reject booleans for integer extra fields by @dajiaohuang in https://github.com/Donkie/Spoolman/pull/1214
* Reject odd-length tag UIDs by @dajiaohuang in https://github.com/Donkie/Spoolman/pull/1231
* Remember the Library page size by @Donkie in https://github.com/Donkie/Spoolman/pull/1284
* Pin Redoc to v2 in generated API docs by @devtechedge in https://github.com/Donkie/Spoolman/pull/1288
* Stop the NFC reader after a single-read scan by @Donkie in https://github.com/Donkie/Spoolman/pull/1283
* feat(nfc): OpenPrintTag NDEF/CBOR codec by @goeland86 in https://github.com/Donkie/Spoolman/pull/1112

## New Contributors
* @IdefixRC made their first contribution in https://github.com/Donkie/Spoolman/pull/1184
* @dajiaohuang made their first contribution in https://github.com/Donkie/Spoolman/pull/1216
* @devtechedge made their first contribution in https://github.com/Donkie/Spoolman/pull/1288
* @goeland86 made their first contribution in https://github.com/Donkie/Spoolman/pull/1112

**Full Changelog**: https://github.com/Donkie/Spoolman/compare/v0.27.0...v0.27.1

## 0.27.0

This release adds NFC/RFID tag support and a round of improvements to the new client.

## Highlights
* **NFC/RFID tags.** Spools and filaments can now have tags linked to them. A tag is keyed on its hardware UID alone, so blank NTAG stickers work, and so do read-only vendor tags like Bambu, Creality, Qidi and Prusa. A reader posts to `/tag/scan` and gets the matching spool or filament back. If you pair a browser with a reader in Settings > Tag Scanning, that browser jumps to the item when you tap the tag. On Android over HTTPS the phone can read tags itself, no reader needed. See the wiki for reader setup with ESPHome and Home Assistant: https://github.com/Donkie/Spoolman/wiki/Tag-scanners
* The library filter menu shows colours and materials and lets you pick several values at once. You can also show filaments you have no spools of.
* The SpoolmanDB search in the filament pickers now pages through its results, so you're no longer stuck with the first batch.
* The add flow separates manufacturer, filament and spool into clear steps. It also offers quick-pick roll sizes and lets you create a new filament while changing what a spool holds.
* The library remembers its grouping and sorting, has resizable columns and can filter by date. Its long toolbar menus are now searchable.
* Label export now supports AML.
* Numeric fields accept decimal commas everywhere.

## Notable fixes
* SQLite searches are now case-insensitive for non-ASCII characters too (#1078 by @romasku).
* Measuring a spool now falls back to the manufacturer's empty spool weight when the spool and filament don't set one (#1164 by @Niko11111).
* The dashboard total weight now shows spool weight instead of filament weight (#1113 by @itCarl).
* Writing a backup now closes the SQLite connections it opens (#1104 by @jpapiez).
* Filtering on a location or other text value that contains a comma now works.
* Labels printed on sheets now keep the right size, shape and orientation.

## What's Changed
* client_v2: make the library list column resizable by @Donkie in https://github.com/Donkie/Spoolman/pull/1039
* client_v2: remember the library's grouping and sorting by @Donkie in https://github.com/Donkie/Spoolman/pull/1041
* client_v2: pluggable label export formats, add AML by @Donkie in https://github.com/Donkie/Spoolman/pull/1042
* client_v2: accept decimal commas in every numeric field by @Donkie in https://github.com/Donkie/Spoolman/pull/1046
* client_v2: separate manufacturer, filament and spool in the add flow by @Donkie in https://github.com/Donkie/Spoolman/pull/1056
* client_v2: filter the library by date by @Donkie in https://github.com/Donkie/Spoolman/pull/1054
* client_v2: quick-pick roll sizes when adding spools by @Donkie in https://github.com/Donkie/Spoolman/pull/1065
* client_v2: bring back translucent filament colors by @Donkie in https://github.com/Donkie/Spoolman/pull/1067
* client_v2: make the long toolbar menus searchable by @Donkie in https://github.com/Donkie/Spoolman/pull/1068
* client_v2: edit the manufacturer's extra fields when the add flow creates one by @Donkie in https://github.com/Donkie/Spoolman/pull/1070
* client_v2: point at missing required fields instead of disabling the add button by @Donkie in https://github.com/Donkie/Spoolman/pull/1071
* client_v2: create a filament while changing what a spool holds by @Donkie in https://github.com/Donkie/Spoolman/pull/1072
* client_v2: filter menu colours, materials, checkmarks and multi-select by @Donkie in https://github.com/Donkie/Spoolman/pull/1094
* fix(database): close the sqlite connections used to write a backup by @jpapiez in https://github.com/Donkie/Spoolman/pull/1104
* chore(client): let prettier respect the working tree's line endings by @jpapiez in https://github.com/Donkie/Spoolman/pull/1105
* client_v2: sort direction, out-of-stock filaments and truncation tooltips by @Donkie in https://github.com/Donkie/Spoolman/pull/1097
* Identify spools by NFC/RFID tags by @Donkie in https://github.com/Donkie/Spoolman/pull/1096
* Replace Ko-fi buttons with GitHub Sponsors by @Donkie in https://github.com/Donkie/Spoolman/pull/1111
* fix: dashboard total weight displayes filament weight instead of actual spool weight by @itCarl in https://github.com/Donkie/Spoolman/pull/1113
* Key the tag scan debounce on the resolved match by @Donkie in https://github.com/Donkie/Spoolman/pull/1116
* Offer the reader's last UID in the Add tag dialog by @Niko11111 in https://github.com/Donkie/Spoolman/pull/1120
* Keep the spool weight unit on one line in the library list by @Donkie in https://github.com/Donkie/Spoolman/pull/1160
* Page through SpoolmanDB search results in the filament pickers by @Donkie in https://github.com/Donkie/Spoolman/pull/1161
* fix(labels): page the print tab's spool list by @Donkie in https://github.com/Donkie/Spoolman/pull/1163
* fix(api): keep quoted string filter terms whole when they contain commas by @Donkie in https://github.com/Donkie/Spoolman/pull/1185
* Resolve the empty spool weight up to the vendor when measuring by @Niko11111 in https://github.com/Donkie/Spoolman/pull/1164
* fix: make SQLite searches Unicode case-insensitive by @romasku in https://github.com/Donkie/Spoolman/pull/1078

## New Contributors
* @jpapiez made their first contribution in https://github.com/Donkie/Spoolman/pull/1104
* @itCarl made their first contribution in https://github.com/Donkie/Spoolman/pull/1113
* @Niko11111 made their first contribution in https://github.com/Donkie/Spoolman/pull/1120
* @romasku made their first contribution in https://github.com/Donkie/Spoolman/pull/1078

**Full Changelog**: https://github.com/Donkie/Spoolman/compare/v0.26.1...v0.27.0

## 0.26.1
- Upgraded base image to official `ghcr.io/donkie/spoolman:latest` (v0.26.1).
- Added automatic persistent storage in `/config/spoolman/spoolman.db`.
- Multi-arch support (`amd64`, `aarch64`, `armv7`, `i386`).
