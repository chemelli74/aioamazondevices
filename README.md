# aioamazondevices

<p align="center">
  <a href="https://github.com/chemelli74/aioamazondevices/actions/workflows/ci.yml?query=branch%3Amain">
    <img src="https://img.shields.io/github/actions/workflow/status/chemelli74/aioamazondevices/ci.yml?branch=main&label=CI&logo=github&style=flat-square" alt="CI Status" >
  </a>
  <a href="https://codecov.io/gh/chemelli74/aioamazondevices">
    <img src="https://img.shields.io/codecov/c/github/chemelli74/aioamazondevices.svg?logo=codecov&logoColor=fff&style=flat-square" alt="Test coverage percentage">
  </a>
</p>
<p align="center">
  <a href="https://python-poetry.org/">
    <img src="https://img.shields.io/badge/packaging-poetry-299bd7?style=flat-square&logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA4AAAASCAYAAABrXO8xAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAJJSURBVHgBfZLPa1NBEMe/s7tNXoxW1KJQKaUHkXhQvHgW6UHQQ09CBS/6V3hKc/AP8CqCrUcpmop3Cx48eDB4yEECjVQrlZb80CRN8t6OM/teagVxYZi38+Yz853dJbzoMV3MM8cJUcLMSUKIE8AzQ2PieZzFxEJOHMOgMQQ+dUgSAckNXhapU/NMhDSWLs1B24A8sO1xrN4NECkcAC9ASkiIJc6k5TRiUDPhnyMMdhKc+Zx19l6SgyeW76BEONY9exVQMzKExGKwwPsCzza7KGSSWRWEQhyEaDXp6ZHEr416ygbiKYOd7TEWvvcQIeusHYMJGhTwF9y7sGnSwaWyFAiyoxzqW0PM/RjghPxF2pWReAowTEXnDh0xgcLs8l2YQmOrj3N7ByiqEoH0cARs4u78WgAVkoEDIDoOi3AkcLOHU60RIg5wC4ZuTC7FaHKQm8Hq1fQuSOBvX/sodmNJSB5geaF5CPIkUeecdMxieoRO5jz9bheL6/tXjrwCyX/UYBUcjCaWHljx1xiX6z9xEjkYAzbGVnB8pvLmyXm9ep+W8CmsSHQQY77Zx1zboxAV0w7ybMhQmfqdmmw3nEp1I0Z+FGO6M8LZdoyZnuzzBdjISicKRnpxzI9fPb+0oYXsNdyi+d3h9bm9MWYHFtPeIZfLwzmFDKy1ai3p+PDls1Llz4yyFpferxjnyjJDSEy9CaCx5m2cJPerq6Xm34eTrZt3PqxYO1XOwDYZrFlH1fWnpU38Y9HRze3lj0vOujZcXKuuXm3jP+s3KbZVra7y2EAAAAAASUVORK5CYII=" alt="Poetry">
  </a>
  <a href="https://github.com/ambv/black">
    <img src="https://img.shields.io/badge/code%20style-black-000000.svg?style=flat-square" alt="black">
  </a>
  <a href="https://github.com/pre-commit/pre-commit">
    <img src="https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white&style=flat-square" alt="pre-commit">
  </a>
</p>
<p align="center">
  <a href="https://pypi.org/project/aioamazondevices/">
    <img src="https://img.shields.io/pypi/v/aioamazondevices.svg?logo=python&logoColor=fff&style=flat-square" alt="PyPI Version">
  </a>
  <img src="https://img.shields.io/pypi/pyversions/aioamazondevices.svg?style=flat-square&logo=python&amp;logoColor=fff" alt="Supported Python versions">
  <img src="https://img.shields.io/pypi/l/aioamazondevices.svg?style=flat-square" alt="License">
</p>

---

**Source Code**: <a href="https://github.com/chemelli74/aioamazondevices" target="_blank">https://github.com/chemelli74/aioamazondevices </a>

---

Python library to control Amazon devices

## Installation

Install this via pip (or your favourite package manager):

`pip install aioamazondevices`

## Test

Test the library with:

`python library_test.py`

The script accept command line arguments or a library_test.json config file:

```json
{
  "country": "IT",
  "email": "<my_address@gmail.com>",
  "password": "<my_password>",
  "single_device_name": "Echo Dot Livingroom",
  "cluster_device_name": "Everywhere",
  "login_data_file": "out/login_data.json",
  "save_raw_data": true,
  "test": true
}
```

## Known Issues & Limitations

See [wiki](https://github.com/chemelli74/aioamazondevices/wiki/Known-Issues-and-Limitations)

## Unknown device type

See [wiki](https://github.com/chemelli74/aioamazondevices/wiki/Unknown-Device-Types)

## Roadmap

See [wiki](https://github.com/chemelli74/aioamazondevices/wiki/Roadmap)

## Contributors ✨

Thanks goes to these wonderful people ([emoji key](https://allcontributors.org/docs/en/emoji-key)):

<!-- prettier-ignore-start -->
<!-- readme: contributors -start -->
<table>
	<tbody>
		<tr>
            <td align="center">
                <a href="https://github.com/chemelli74">
                    <img src="https://avatars.githubusercontent.com/u/57354320?v=4" width="100;" alt="chemelli74"/>
                    <br />
                    <sub><b>Simone Chemelli</b></sub>
                </a>
            </td>
            <td align="center">
                <a href="https://github.com/jeeftor">
                    <img src="https://avatars.githubusercontent.com/u/6491743?v=4" width="100;" alt="jeeftor"/>
                    <br />
                    <sub><b>Jeef</b></sub>
                </a>
            </td>
            <td align="center">
                <a href="https://github.com/jamesonuk">
                    <img src="https://avatars.githubusercontent.com/u/1040621?v=4" width="100;" alt="jamesonuk"/>
                    <br />
                    <sub><b>jameson_uk</b></sub>
                </a>
            </td>
            <td align="center">
                <a href="https://github.com/ivanfmartinez">
                    <img src="https://avatars.githubusercontent.com/u/677001?v=4" width="100;" alt="ivanfmartinez"/>
                    <br />
                    <sub><b>Ivan F. Martinez</b></sub>
                </a>
            </td>
            <td align="center">
                <a href="https://github.com/AzonInc">
                    <img src="https://avatars.githubusercontent.com/u/11911587?v=4" width="100;" alt="AzonInc"/>
                    <br />
                    <sub><b>Flo</b></sub>
                </a>
            </td>
            <td align="center">
                <a href="https://github.com/lchavezcuu">
                    <img src="https://avatars.githubusercontent.com/u/22165856?v=4" width="100;" alt="lchavezcuu"/>
                    <br />
                    <sub><b>Luis Chavez</b></sub>
                </a>
            </td>
		</tr>
		<tr>
            <td align="center">
                <a href="https://github.com/tronikos">
                    <img src="https://avatars.githubusercontent.com/u/9987465?v=4" width="100;" alt="tronikos"/>
                    <br />
                    <sub><b>tronikos</b></sub>
                </a>
            </td>
		</tr>
	<tbody>
</table>
<!-- readme: contributors -end -->
<!-- prettier-ignore-end -->

This project follows the [all-contributors](https://github.com/all-contributors/all-contributors) specification. Contributions of any kind welcome!

## Credits

This package was created with
[Copier](https://copier.readthedocs.io/) and the
[browniebroke/pypackage-template](https://github.com/browniebroke/pypackage-template)
project template.
