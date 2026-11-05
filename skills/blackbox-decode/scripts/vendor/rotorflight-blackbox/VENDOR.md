# Vendored: Rotorflight Blackbox Explorer parser

These nine files are copied **unmodified** from `js/` of
[rotorflight/rotorflight-blackbox](https://github.com/rotorflight/rotorflight-blackbox) at tag
`release/2.3.0` (commit `b9635a975e95159faf1bf7b5efc4ce7cd93a2b37`, supports firmware up to 4.6).
They are GPL-3.0 like the rest of this repository; see [LICENSE](LICENSE).

Never edit them here. Browser shims that Node needs live in `../../bbl.js`.

| File | sha256 |
| --- | --- |
| cache.js | 1919263ef164f1c75c22760394809e97592bcf301d9ffc4a4fda544093262929 |
| datastream.js | 7f16817c7a73e5effa224ffc38821e46ca8d9fe1537188de1be86eb4cc700768 |
| decoders.js | 35d20cd2966f70df8f109bf2b1e77d253802d89447076507bc3d47d51f8b0b34 |
| flightlog.js | 929babae6c9bf4c6a5f678449b815a659f9c5f0dcd3718a266e60bff5d7aad14 |
| flightlog_fielddefs.js | 98bdbc975211282afd36a38d829a71e7405d7d071b5437ddc6f116d6f31d29c9 |
| flightlog_fields_presenter.js | 236dacda13184bcb3f5d612ee801d4b5a998b5cf290cb048cb876c0666fc7026 |
| flightlog_index.js | 6818fb14f07dd199d6ea37e6ebf4d7e5d4b0a4ed19db6ecf746efdd9957d9fd1 |
| flightlog_parser.js | 9acc23d3819498dca4f40a03ddca3ca5a6fc56ac94dc3fbee0031fc58da010a8 |
| tools.js | 7daacae36945cddef2bb5b2b6cef96b63c8b6ae9436c7e27c52fb0edd1a9aa76 |

## Updating

When a new Blackbox Explorer release supports a newer firmware (the field definitions branch on
`semver.gte(firmwareVersion, ...)`; a log from a newer firmware is decoded with the newest branch
there is):

```sh
git clone --depth 1 --branch release/<x.y.z> https://github.com/rotorflight/rotorflight-blackbox.git /tmp/rfbb
for f in tools cache datastream decoders flightlog_fielddefs flightlog_fields_presenter \
         flightlog_parser flightlog_index flightlog; do cp /tmp/rfbb/js/$f.js .; done
sha256sum *.js     # update the table above, the tag and the commit
python ../../selftest.py <some .bbl files>
```

If a new release needs another file from `js/`, add it to `SCRIPTS` in `bbl.js` in load order.
