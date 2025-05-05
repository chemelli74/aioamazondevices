# Changelog

## v1.7.0 (2025-05-05)

### Features

- Add call_alexa_music() method (#170) ([`9131e5c`](https://github.com/chemelli74/aioamazondevices/commit/9131e5c4323444bc75ce9eef033e1eb3f5048515))


### Testing

- Fix find device in library_test (#171) ([`8afc7a7`](https://github.com/chemelli74/aioamazondevices/commit/8afc7a73f45b71a83a923e8697858b23d368b2b1))


## v1.6.0 (2025-05-05)

### Features

- Add call_alexa_sound() method (#169) ([`d304d14`](https://github.com/chemelli74/aioamazondevices/commit/d304d14fefc195fc510727e86496b8eee8483083))


### Refactoring

- Introduce amazonsequencetype and optimize library_test code (#168) ([`dffbcdc`](https://github.com/chemelli74/aioamazondevices/commit/dffbcdcd2bd7dc933cfaf453adedccbbb8059267))
- Introduce base_payload (#167) ([`51177ae`](https://github.com/chemelli74/aioamazondevices/commit/51177ae0bea90090712e7d7c7d3e1b4724a2a04b))


### Build system

- Bump python-semantic-release/python-semantic-release from 9.21.0 to 9.21.1 (#166) ([`a8cee32`](https://github.com/chemelli74/aioamazondevices/commit/a8cee327f7fbf3da73720936be85d9a4891255c0))
- Bump orjson from 3.10.16 to 3.10.18 (#165) ([`6bcfc64`](https://github.com/chemelli74/aioamazondevices/commit/6bcfc64d7ec716a1f5fe33b8983e696adfeb71bc))


## v1.5.0 (2025-05-04)

### Features

- Add call_alexa_announcement() method (#155) ([`047b335`](https://github.com/chemelli74/aioamazondevices/commit/047b3357d56387cfd2102ee9d41fd67cc40fc8f4))


## v1.4.2 (2025-05-03)

### Bug fixes

- Improve aiohttp support (#161) ([`8ffdc7f`](https://github.com/chemelli74/aioamazondevices/commit/8ffdc7f746848db15fd3affcdca68a04bc196db3))


## v1.4.1 (2025-05-02)

### Bug fixes

- Force file encoding for windows compatibility (#159) ([`e0b952c`](https://github.com/chemelli74/aioamazondevices/commit/e0b952c62c0c8e8383999c29ec4a285771460c2b))


### Build system

- Add more files to cleanup script (#158) ([`9895f4a`](https://github.com/chemelli74/aioamazondevices/commit/9895f4a5aa5c86906c00dfeef862ec410fb69ecd))
- Cleanup script (#156) ([`1b5c22f`](https://github.com/chemelli74/aioamazondevices/commit/1b5c22f8669a218cc64074f1f747de1476433b7b))


## v1.4.0 (2025-04-29)

### Features

- Move from httpx to aiohttp (#151) ([`7471c2b`](https://github.com/chemelli74/aioamazondevices/commit/7471c2b1a25726be2b3b23f1a109115f27a36ec8))


### Build system

- Cleanup after #134 (#154) ([`c7bc2dd`](https://github.com/chemelli74/aioamazondevices/commit/c7bc2dd846052559dfab1272d2941608885040f8))


## v1.3.0 (2025-04-27)

### Features

- Add call_alexa_speak() method (#98) ([`1e83769`](https://github.com/chemelli74/aioamazondevices/commit/1e8376985d6ee9e5ad6624c06be1ea412ca57ef2))


## v1.2.0 (2025-04-26)

### Features

- Add session auth status (#152) ([`d91cc50`](https://github.com/chemelli74/aioamazondevices/commit/d91cc5034d4be05931420bacbe433e85c4f67491))


### Unknown

## v1.1.0 (2025-04-25)

### Features

- Replace session.post with _session_request (#149) ([`55aa4eb`](https://github.com/chemelli74/aioamazondevices/commit/55aa4eb29123dd98bc5facc8d7d097bf6bc9bdfc))


### Build system

- Bump h11 from 0.14.0 to 0.16.0 (#147) ([`e3b90e1`](https://github.com/chemelli74/aioamazondevices/commit/e3b90e10bcd654f47dee7cc81596fdce9ac095d6))
- Improve environment (#146) ([`718dd03`](https://github.com/chemelli74/aioamazondevices/commit/718dd03c258864335ead34cec080228773e87f25))
- Bump rsa from 4.9 to 4.9.1 (#144) ([`4d7ed78`](https://github.com/chemelli74/aioamazondevices/commit/4d7ed78e46f149897ee179b582df02b277ca35d8))
- Bump beautifulsoup4 from 4.13.3 to 4.13.4 (#143) ([`23a15c9`](https://github.com/chemelli74/aioamazondevices/commit/23a15c9891e35867b18ce10acd8e4dc963387980))
- Bump pytest-cov from 6.0.0 to 6.1.1 (#139) ([`0c5e05c`](https://github.com/chemelli74/aioamazondevices/commit/0c5e05c9e741742bda06694c46ad68590118de6c))
- Bump orjson from 3.10.15 to 3.10.16 (#137) ([`5d5aeec`](https://github.com/chemelli74/aioamazondevices/commit/5d5aeecacd6133b2fcbb0bfddce9f0e6426ba89c))
- Ruff rules update (#133) ([`62f92fb`](https://github.com/chemelli74/aioamazondevices/commit/62f92fb86bd9599dda0652d5fcda67ab11a3e3ef))
- Bump pytest from 8.3.4 to 8.3.5 (#129) ([`99264b6`](https://github.com/chemelli74/aioamazondevices/commit/99264b6ef309e7b314cafe0b6c4cd96ef7ee02bd))
- Bump python-semantic-release/python-semantic-release from 9.20.0 to 9.21.0 (#127) ([`fcae1ba`](https://github.com/chemelli74/aioamazondevices/commit/fcae1ba30692c5b5dd0236464eeaca240123e81f))
- Bump python-semantic-release/python-semantic-release from 9.19.1 to 9.20.0 (#125) ([`6c8fe74`](https://github.com/chemelli74/aioamazondevices/commit/6c8fe749c83e0642f46de9538df49768c9b23ca1))
- Bump python-semantic-release/python-semantic-release from 9.19.0 to 9.19.1 (#124) ([`b7034ee`](https://github.com/chemelli74/aioamazondevices/commit/b7034ee8baba22aaf0ed23f16ba4f17de6fcda2c))
- Bump python-semantic-release/python-semantic-release from 9.18.0 to 9.19.0 (#122) ([`d36c277`](https://github.com/chemelli74/aioamazondevices/commit/d36c2771227d9e07d5286dfe064271bc0732fc79))
- Bump beautifulsoup4 from 4.13.0 to 4.13.3 (#121) ([`483ae44`](https://github.com/chemelli74/aioamazondevices/commit/483ae446f913ce7d1e07f934cda20190697fad44))
- Bump python-semantic-release/python-semantic-release from 9.17.0 to 9.18.0 (#119) ([`2f18c9a`](https://github.com/chemelli74/aioamazondevices/commit/2f18c9acf3798835645ade2dbd949c05bbff650d))
- Bump beautifulsoup4 from 4.12.3 to 4.13.0 (#117) ([`04e3c8c`](https://github.com/chemelli74/aioamazondevices/commit/04e3c8c33853702e14540717559191bf1aba8974))
- Bump python-semantic-release/python-semantic-release from 9.16.1 to 9.17.0 (#115) ([`e5f147c`](https://github.com/chemelli74/aioamazondevices/commit/e5f147cd50d4e0c072b034124a974249d7723dcd))
- Bump orjson from 3.10.14 to 3.10.15 (#113) ([`fd3c424`](https://github.com/chemelli74/aioamazondevices/commit/fd3c424999e0b634dec72d927befe2881d6b95b2))
- Bump wagoid/commitlint-github-action from 6.2.0 to 6.2.1 (#112) ([`43cc69a`](https://github.com/chemelli74/aioamazondevices/commit/43cc69ad50e163d99bbe3cdb61ecff08ec870c0b))
- Bump python-semantic-release/python-semantic-release from 9.15.2 to 9.16.1 (#110) ([`799a6a4`](https://github.com/chemelli74/aioamazondevices/commit/799a6a4ec773fd4ac045029fb45e1af6d83f25da))
- Bump orjson from 3.10.13 to 3.10.14 (#111) ([`e721a89`](https://github.com/chemelli74/aioamazondevices/commit/e721a8996c0a967791376a54f9b309302e4b4b7c))
- Bump orjson from 3.10.12 to 3.10.13 (#108) ([`42c4703`](https://github.com/chemelli74/aioamazondevices/commit/42c4703f524a4b86829a478cc96dc2c3bc1c1cc1))
- Bump wagoid/commitlint-github-action from 6.1.2 to 6.2.0 (#105) ([`9d976f0`](https://github.com/chemelli74/aioamazondevices/commit/9d976f00a1df3bf5484d7f3a35244732cbcc4571))
- Bump python-semantic-release/python-semantic-release from 9.15.1 to 9.15.2 (#103) ([`312f6a0`](https://github.com/chemelli74/aioamazondevices/commit/312f6a08415274eabf1649d123d53ef4441eb064))


### Refactoring

- Removed unneeded auth (#134) ([`e90e87d`](https://github.com/chemelli74/aioamazondevices/commit/e90e87d8e8c37ccf0b6017dad838a71529a65b4b))


### Testing

- Fix library_test args (#107) ([`a317ee0`](https://github.com/chemelli74/aioamazondevices/commit/a317ee0b44a8c13493c845172a1346b2b870be65))


## v1.0.0 (2024-12-09)

### Bug fixes

- Use iso 3166 standard for country codes (#102) ([`0fa4e96`](https://github.com/chemelli74/aioamazondevices/commit/0fa4e968678e13c34d1352e7b53cd5224b533779))


### Build system

- Bump httpx from 0.28.0 to 0.28.1 (#99) ([`c853dc3`](https://github.com/chemelli74/aioamazondevices/commit/c853dc3fe5c0e75491152f7cd9592ff03c79a717))


## v0.13.0 (2024-12-03)

### Features

- Load login data from dict (#97) ([`d881d16`](https://github.com/chemelli74/aioamazondevices/commit/d881d16d5d4331217b323f80ee69a6c357a16028))


### Build system

- Bump python-semantic-release/python-semantic-release from 9.15.0 to 9.15.1 (#96) ([`ef13a01`](https://github.com/chemelli74/aioamazondevices/commit/ef13a012a0e46468547be4b01952c49fcc90a4f6))


## v0.12.0 (2024-12-02)

### Features

- Return parsed devices data (#94) ([`114da17`](https://github.com/chemelli74/aioamazondevices/commit/114da17ce89a5c521eeff91f8590cfe61a55fce9))


## v0.11.1 (2024-12-02)

### Bug fixes

- Properties for amazondevice class (#93) ([`a0a2af6`](https://github.com/chemelli74/aioamazondevices/commit/a0a2af69d53433a351ed468f5b607dd562f3319e))


## v0.11.0 (2024-12-02)

### Features

- Add device models (#92) ([`8baaa6b`](https://github.com/chemelli74/aioamazondevices/commit/8baaa6ba47059b00c38afb4d2ae2716219ac8fa9))


### Build system

- Bump python-semantic-release/python-semantic-release from 9.14.0 to 9.15.0 (#91) ([`d20c580`](https://github.com/chemelli74/aioamazondevices/commit/d20c5802c9438dda1172e616978eda356f4d6ad3))
- Bump pytest from 8.3.3 to 8.3.4 (#90) ([`711373d`](https://github.com/chemelli74/aioamazondevices/commit/711373df071b22463742ce6b4af744b385ff59e1))
- Bump httpx from 0.27.2 to 0.28.0 (#89) ([`923ed8c`](https://github.com/chemelli74/aioamazondevices/commit/923ed8c9c9e9e052cfc87818d365e5b82e6ca33d))
- Bump orjson from 3.10.11 to 3.10.12 (#87) ([`71482db`](https://github.com/chemelli74/aioamazondevices/commit/71482db191ce4a46b5d6ac3ce7bfe78ae4a2aa6b))
- Bump codecov/codecov-action from 4 to 5 (#85) ([`c92c4f2`](https://github.com/chemelli74/aioamazondevices/commit/c92c4f2ce38d0d4783d103a6cbd275047b9f70d0))


## v0.10.0 (2024-11-13)

### Features

- Add login from stored data (#78) ([`36af872`](https://github.com/chemelli74/aioamazondevices/commit/36af8723723ef7a4257230cb548d416614a82b8c))


### Build system

- Bump python-semantic-release/python-semantic-release (#83) ([`b39e995`](https://github.com/chemelli74/aioamazondevices/commit/b39e995e5d74adb3098f6a1049244021d087fccc))


### Refactoring

- Small headers cleanup (#82) ([`e4fafe1`](https://github.com/chemelli74/aioamazondevices/commit/e4fafe1b18889413249fe51d1d680eb0eb7856a5))


## v0.9.0 (2024-11-10)

### Features

- Devices cleanup and data consolidation (#81) ([`d6a911c`](https://github.com/chemelli74/aioamazondevices/commit/d6a911cc1a28fa269fa158bf1ee60860a421be4a))
- Add library_test data saving (#80) ([`12f0cc8`](https://github.com/chemelli74/aioamazondevices/commit/12f0cc88bef2a8b88e4f4fc44b5243ade5b1c303))


### Refactoring

- Renamed param and var to a better naming (#77) ([`d5f4da6`](https://github.com/chemelli74/aioamazondevices/commit/d5f4da677c26b419c959c9b1b925f09afaf21f8e))


### Testing

- Add more vscode launch options (#76) ([`fdac075`](https://github.com/chemelli74/aioamazondevices/commit/fdac075e54ad78600db4e3069e71c5f0051ec803))
- Add .coveragerc (#69) ([`d3cbc5e`](https://github.com/chemelli74/aioamazondevices/commit/d3cbc5e5e279c08491bb3d93851f5703b0e2b053))


### Build system

- Bump python-semantic-release/python-semantic-release (#75) ([`520b94a`](https://github.com/chemelli74/aioamazondevices/commit/520b94a29e3aeff2668ce47d152daf97e7911340))
- Bump python-semantic-release/python-semantic-release (#74) ([`61b9c65`](https://github.com/chemelli74/aioamazondevices/commit/61b9c655af1f5252e521c2b3c9656b432aace1c4))
- Bump orjson from 3.10.10 to 3.10.11 (#72) ([`850e41f`](https://github.com/chemelli74/aioamazondevices/commit/850e41ff986c28d1ad00c78235f78ff4240388ae))
- Bump pytest-cov from 5.0.0 to 6.0.0 (#71) ([`5871ed5`](https://github.com/chemelli74/aioamazondevices/commit/5871ed5dc8d68b08aa78b021ad77bcb904beaf9a))
- Bump colorlog from 6.8.2 to 6.9.0 (#70) ([`29a9c7b`](https://github.com/chemelli74/aioamazondevices/commit/29a9c7b5273454651d4b0eeb7312ba81fbfdc1ad))


## v0.8.0 (2024-11-01)

### Build system

- Revert to standard semantic release (#67) ([`874b330`](https://github.com/chemelli74/aioamazondevices/commit/874b330d0faf4c8248fb007f9c67ad61bceadfd8))


### Features

- Drop python 3.11 support (#66) ([`317ba8d`](https://github.com/chemelli74/aioamazondevices/commit/317ba8d90ca55bac1c344170762e799a22cca449))


## v0.7.3 (2024-10-31)

### Unknown

### Bug fixes

- Fix license classifier ([`f5af1f8`](https://github.com/chemelli74/aioamazondevices/commit/f5af1f859ea60ddcdf0d5e599b38e147f172bfe7))


### Build system

- Add python 3.13 ([`21b0e3b`](https://github.com/chemelli74/aioamazondevices/commit/21b0e3b2b6c9bed3185287588f2ff08f496b698c))
- Bump orjson from 3.10.9 to 3.10.10 ([`2540404`](https://github.com/chemelli74/aioamazondevices/commit/25404040807718998efd6ed5a0765879e0a04948))


## v0.7.2 (2024-10-22)

### Unknown

### Bug fixes

- Avoid registering a new device at each login cicle ([`0681a85`](https://github.com/chemelli74/aioamazondevices/commit/0681a8566b8856f940ef1bc910bdc9f6adb8a905))


## v0.7.1 (2024-10-22)

### Unknown

### Bug fixes

- Allow different openid.assoc_handle by country ([`c0b7249`](https://github.com/chemelli74/aioamazondevices/commit/c0b724908298f06b30352fb9b83c52eea5129517))


### Build system

- Bump orjson from 3.10.7 to 3.10.9 ([`5062556`](https://github.com/chemelli74/aioamazondevices/commit/5062556efa2b6cecab4fecdbf339ffd69cb82ded))
- Pre-commit migrate-config ([`07ae187`](https://github.com/chemelli74/aioamazondevices/commit/07ae187e21e91546b7ac9bd33b256ede8f3b3550))
- Exclude out folder ([`5065cd4`](https://github.com/chemelli74/aioamazondevices/commit/5065cd45461d250ebb7693c7577b3dd8282b3874))
- Add commitlint to devcontainer ([`8eeeed6`](https://github.com/chemelli74/aioamazondevices/commit/8eeeed6fe83c4a82fe05dcb9a5241fea60bf1f05))
- Adding a shell.nix so you can do nix-shell to work on this repo ([`57dfa5a`](https://github.com/chemelli74/aioamazondevices/commit/57dfa5a40ada28cf9ce2eb78b63d212a042017b5))


## v0.7.0 (2024-10-08)

### Unknown

## v0.6.0 (2024-10-08)

### Unknown

### Bug fixes

- Restore .gitignore from main branch ([`1c620c5`](https://github.com/chemelli74/aioamazondevices/commit/1c620c5363cc610fed2ca76f6265175890b225b4))


### Features

- Rebase onto main ([`dc09f14`](https://github.com/chemelli74/aioamazondevices/commit/dc09f1451d0a9525abe0abc9541c294f2288724c))
- Updated logic to find form ([`8322efc`](https://github.com/chemelli74/aioamazondevices/commit/8322efcf15cfa307bf8ebf8152f93b4e775bff2d))


## v0.5.1 (2024-10-08)

### Unknown

### Bug fixes

- Removed .idea directory - was accidently committetd ([`716b221`](https://github.com/chemelli74/aioamazondevices/commit/716b221d2082880a88767f367db3a1676a99371d))


## v0.5.0 (2024-10-08)

### Unknown

### Features

- Adding commitlint hook ([`96d9fc4`](https://github.com/chemelli74/aioamazondevices/commit/96d9fc41341c0b13851a17622e99368c7a90f954))


## v0.4.0 (2024-10-08)

### Unknown

### Features

- Modified output functionality ([`141e57a`](https://github.com/chemelli74/aioamazondevices/commit/141e57a9d9145bb4ec5f6ff484336c3f82cec083))


## v0.3.0 (2024-10-08)

### Unknown

### Features

- Update gitignore information for pycharm ([`8701548`](https://github.com/chemelli74/aioamazondevices/commit/8701548d2a06c8c9ded7cc6d277a0bcb4905c832))
- Device registration ([`d66a054`](https://github.com/chemelli74/aioamazondevices/commit/d66a05462f16caa35e94532301a42f519922354c))


## v0.2.0 (2024-10-03)

### Unknown

### Features

- Save html response code to disk ([`2c54b4b`](https://github.com/chemelli74/aioamazondevices/commit/2c54b4b5db16e9cb706cef47a98112c2ba0101fc))


### Build system

- Bump pytest from 8.3.2 to 8.3.3 ([`75abdc5`](https://github.com/chemelli74/aioamazondevices/commit/75abdc5d7095ee656d4f3acf562e2b3c43bb4239))
- Bump tiangolo/issue-manager from 0.5.0 to 0.5.1 ([`f8a4c86`](https://github.com/chemelli74/aioamazondevices/commit/f8a4c86709e151b355be20cc1d786649a4a28ddf))
- Bump wagoid/commitlint-github-action from 6.1.1 to 6.1.2 ([`fb8156c`](https://github.com/chemelli74/aioamazondevices/commit/fb8156c99bc31f2ace979b3532f05a4af9dae84d))
- Bump httpx from 0.27.0 to 0.27.2 ([`18fe00f`](https://github.com/chemelli74/aioamazondevices/commit/18fe00f07108829463256851ba18bb6d4bef269a))
- Bump wagoid/commitlint-github-action from 6.0.2 to 6.1.1 ([`dbb2d2e`](https://github.com/chemelli74/aioamazondevices/commit/dbb2d2ef32005930d12beb2168b8f7280128b5a8))
- Bump orjson from 3.10.6 to 3.10.7 ([`8652e0d`](https://github.com/chemelli74/aioamazondevices/commit/8652e0dd50ce8fee3406da575691ae9247152133))
- Bump wagoid/commitlint-github-action from 6.0.1 to 6.0.2 ([`4ea8e37`](https://github.com/chemelli74/aioamazondevices/commit/4ea8e37fab352aed837fe90dd73d7609d6914eee))
- Bump snok/install-poetry from 1.3.4 to 1.4.1 ([`6d448c4`](https://github.com/chemelli74/aioamazondevices/commit/6d448c4367141025986f651986e3e84babac3562))
- Bump pytest from 8.3.1 to 8.3.2 ([`4e95b0c`](https://github.com/chemelli74/aioamazondevices/commit/4e95b0ceb3192ffb30ee2b42bb45786a657f1e17))
- Bump pytest from 8.2.2 to 8.3.1 ([`3d9958a`](https://github.com/chemelli74/aioamazondevices/commit/3d9958a6bf5e3943f1daee0746f95434388d7ad7))
- Bump orjson from 3.10.5 to 3.10.6 ([`afd2a6a`](https://github.com/chemelli74/aioamazondevices/commit/afd2a6afe617eb150866941b0c98fbdb43f03a18))
- Bump certifi from 2024.6.2 to 2024.7.4 ([`585a3c1`](https://github.com/chemelli74/aioamazondevices/commit/585a3c126fd6bc8047ffd16c2a582ed64a3424fd))
- Bump orjson from 3.10.3 to 3.10.5 ([`1ce4a95`](https://github.com/chemelli74/aioamazondevices/commit/1ce4a95a57f71327194803dfa8d014384bf18f71))


## v0.1.1 (2024-05-22)

### Unknown

### Bug fixes

- Force country code lower case ([`8951bf9`](https://github.com/chemelli74/aioamazondevices/commit/8951bf93c9f80e3fa5a6da23fcaeceb71ca457e2))


### Build system

- Bump pytest from 8.2.0 to 8.2.1 ([`404fe7f`](https://github.com/chemelli74/aioamazondevices/commit/404fe7fbc195d653437f60ec4db651cac69af82b))


## v0.1.0 (2024-05-07)

### Unknown

### Features

- First coding ([`a407a5e`](https://github.com/chemelli74/aioamazondevices/commit/a407a5e66d48ba4ea6307a5fd161ab8397f7b54b))


### Build system

- Bump pytest from 8.1.1 to 8.2.0 ([`025f860`](https://github.com/chemelli74/aioamazondevices/commit/025f8603fe123514f5b967138133871160db60c2))


## v0.0.0 (2024-04-24)

### Unknown

### Build system

- Cleanup ([`1828b57`](https://github.com/chemelli74/aioamazondevices/commit/1828b57f314940c2679d700dad5950c359d0aeaf))
- Bump codecov/codecov-action from 3 to 4 ([`552b4d9`](https://github.com/chemelli74/aioamazondevices/commit/552b4d9f1d80b59f05c65681da13ab84d9a9145e))
- Bump pytest-cov from 3.0.0 to 5.0.0 ([`4834921`](https://github.com/chemelli74/aioamazondevices/commit/48349214aadf5309bb671a8abd6ad3b6c2ff676b))
- Bump pytest from 7.4.4 to 8.1.1 ([`9e12952`](https://github.com/chemelli74/aioamazondevices/commit/9e12952a785f269437d33f65eba0481481a3d075))
- Mypy and prettier fixes ([`e9a1903`](https://github.com/chemelli74/aioamazondevices/commit/e9a1903d9cace7984b264dad44586f4b4bb53e46))
- Configure base tools ([`ff0481b`](https://github.com/chemelli74/aioamazondevices/commit/ff0481be810f5c7a10265ad86e7299d6d023b727))
