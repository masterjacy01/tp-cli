# @masterjacy01/tp-cli

Seamless installer wrapper for the Python-based `tp-cli`.

## Usage

Install from PyPI (after release):

```bash
npx -y @masterjacy01/tp-cli install tp-cli
```

Install directly from GitHub:

```bash
npx -y @masterjacy01/tp-cli install git+https://github.com/masterjacy01/tp-cli.git
```

The installer prefers `pipx` and falls back to `python3 -m pip`.

You can also run the binary name explicitly:

```bash
npx -y -p @masterjacy01/tp-cli tp-cli install git+https://github.com/masterjacy01/tp-cli.git
```
