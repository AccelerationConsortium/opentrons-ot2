# Opentrons OT-2

A SiLA2 connector for the Opentrons OT-2 liquid handling robot

## Getting Started

### Prerequisites

Ensure that Python 3.10 or newer is installed on your system. You can download Python from the official website [python.org](https://www.python.org/downloads/).

### Installation

#### Create a Virtual Environment

It is highly recommended to use a virtual environment to manage the dependencies for your connector project. This keeps the dependencies for different connectors isolated from each other. Use the following command to create a virtual environment:

```sh
python -m venv venv
```

Activate the virtual environment:

- On **Windows**:

  ```sh
  .\venv\Scripts\activate.bat
  ```

- On **macOS**/**Linux**:

  ```sh
  source venv/bin/activate
  ```

If you are on a Windows machine, you may additionally wish to set the `UNITELABS_CDK_APP` environment variable to the connector's entry point. This can be done by running the following command:

```sh
set UNITELABS_CDK_APP=unitelabs.opentrons_ot2:create_app
```

Setting this environment variable will allow you to run varous CLI commands without providing `--app unitelabs.opentrons_ot2:create_app` every time.

#### Install Required Dependencies

Install the necessary Python packages into your active virtual environment. Use pip to download the connector along with its dependencies:

```sh
python -m pip install unitelabs-opentrons-ot2 \
  --index-url https://gitlab.com/api/v4/groups/1009252/-/packages/pypi/simple
```

If you are working with a private connector repository, authenticate pip to allow access:

```sh
python -m pip install unitelabs-opentrons-ot2 \
  --index-url https://<username>:<password>@gitlab.com/api/v4/groups/1009252/-/packages/pypi/simple
```

#### Configure the Connector

To get information about the configuration values for the connector simply run:

- On **Windows**:

  ```sh
  config show --app unitelabs.opentrons_ot2:create_app
  ```

- On **macOS**/**Linux**:

  ```sh
  config show
  ```

To create a configuration file for our connector we run:

- On **Windows**:

  ```sh
  config create --app unitelabs.opentrons_ot2:create_app
  ```

- On **macOS**/**Linux**:

  ```sh
  config create
  ```

Used as such this command will create a `config.json` in the current working directory. If you prefer to use yaml for your config file or would like to save the file to a different location, simply add the `--path` argument:

- On **Windows**:

  ```sh
  config create --app unitelabs.opentrons_ot2:create_app  --path <path to config>
  ```

- On **macOS**/**Linux**:

  ```sh
  config create --path <path to config>
  ```

The file that is created will be populated with default configuration values that you may now edit.

Note: The `cloud_server_endpoint` values are only necessary if you want to use the connector with the UniteLabs platform.

#### Verify the Installation

After installation, you can verify that everything works by starting the connector using the CLI tool included in the dependencies:

Note: This must be done in the activated environment setup in Step 1.

```sh
connector start --app unitelabs.opentrons_ot2:create_app -vvv
```

If you decided to create your configuration file at a non-default location, you can specify it with the `--config-path` or `-cfg` argument:

```sh
connector start --app unitelabs.opentrons_ot2:create_app -cfg <path to config> -vvv
```

In this way one can have multiple configurations for the same connector.

## Deploying to the OT-2

The OT-2 runs a custom embedded Linux with glibc 2.25 and Python 3.10. Standard PyPI
wheels for C-extension packages are built against much newer glibc versions and will
fail at import with `GLIBC_X.XX not found`. The two affected packages are:

| Package | PyPI wheel requires | Fix |
|---------|-------------------|-----|
| `grpcio` | glibc 2.32+ | Compiled from source on Debian Stretch (glibc 2.24 cap) |
| `rpds-py <0.30` | glibc 2.34+ | Upgrade to ≥0.30, which ships a `manylinux_2_17_armv7l` wheel (glibc 2.17+) |

The `dist_arm/` directory contains a pre-built bundle of all wheels ready for offline
installation on the robot.

### Building `dist_arm/`

Trigger the **Build OT-2 ARM Wheels** GitHub Actions workflow (`.github/workflows/build-ot2-arm-wheels.yml`).
It runs on a native `ubuntu-24.04-arm` runner, so arm32v7 containers execute without
QEMU emulation. The multi-stage `Dockerfile.build` compiles grpcio from source on
Debian Buster to keep glibc symbol requirements within what the OT-2 supports, then
downloads all remaining dependencies as standard wheels.

Download the `ot2-arm-wheels` artifact from the completed run and replace `dist_arm/`.

### Installing on the OT-2

SSH into the robot and copy the `dist_arm/` directory across:

```sh
scp -r dist_arm/ root@<ot2-ip>:/root/
```

Then on the robot:

```sh
bash /root/dist_arm/install.sh
```

This creates a venv at `/opt/sila2_ot2` with `--system-site-packages` so the connector
can access the system `opentrons` package. Start the connector with:

```sh
/opt/sila2_ot2/bin/python -m unitelabs.opentrons_ot2
```

### Why `--system-site-packages`

The `opentrons` package (and its `opentrons-shared-data` companion) are pre-installed
as system packages by Opentrons firmware. They are intentionally excluded from
`dist_arm/` to avoid version conflicts. The venv inherits them via `--system-site-packages`.

## Usage

To interact with the running connector, we recommend using the [SiLA Browser](https://gitlab.com/unitelabs/sila2/sila-browser).

### Encryption

To secure communication between the connector and its clients, you can enable TLS encryption. Start by installing the optional `cryptography` package for generating TLS certificates:

```sh
python -m pip install cryptography
```

To generate a pair of public and private keys, use the following command:

```sh
certificate generate
```

Without any arguments this command uses the default config location to get the connector's UUID and host name, required to generate TLS certificates. It will prompt you as to whether or not you want to update your config file to enable TLS encryption on your connector. This prompt can be suppressed with the use of the `--non-interactive` or `-y` flag, which will update the config file with paths to the locally created files without prompting, or with `--embed` or `-e` flag to write the file contents into the config file directly.

You can adjust your config file's host to reflect the machine's hostname, or set it to `localhost` if the connector should only be accessible locally.

If your config file was created at a non-default path, you can provide it with the `--config-path` or `-cfg` option:

```sh
certificate generate -cfg <path to config>
```

By default the generate command creates the `cert.pem` and `key.pem` files in your current working directory. You can customize the output directory with the `--target` argument.

If you choose not to update your config file with the paths to your certificates using `--non-interactive` or `-y` or to have the file contents saved directly in your config file with `--embed` or `-e` flag, you will have to modify the config file yourself to set the following values under `sila_server`:

- `certificate_chain` - the path to the `cert.pem` file
- `private_key` - the path to the `key.pem` file
- `tls` - a boolean that toggles on/off TLS encryption for the SiLA server

With your updated config file you can once again run:

```sh
connector start --app unitelabs.opentrons_ot2:create_app -vvv
```

> **Important:** Never share the `key.pem` file with anyone. Only the `cert.pem` is required for clients to connect to encrypted servers.

## Contribute

We welcome contributions to improve our connectors. Follow the steps below to set up your development environment.

### Development Environment

We use [uv][] for Python packaging.

#### Set Up the Environment

Install and configure `uv`:

```sh
pipx install uv
```

Note: requires `uv>=0.6.8`.

#### Install the Package

Clone the repository:

```sh
git clone https://github.com/AccelerationConsortium/sila2-ot2.git
```

Set up the development environment and start the connector:

```sh
uv sync --all-extras
uv run connector start -vvv
```

Note: By default, uv will sync all dependencies with every call to `uv run CMD`. To prevent this use `uv run --frozen CMD` or set the environment variable `UV_FROZEN=true`.

#### Install pre-commit Hooks

Set up `pre-commit` hooks to ensure code quality:

```sh
uv run pre-commit install
```

#### Running Tests

To run the test suite:

```sh
uv run pytest
```

To run tests with a specific version of python, e.g. Python 3.12:

```sh
uv run --python 3.12 --all-extras pytest
```

#### Dev-Mode

To improve the development experience, we recommend running the connector in developer mode. This will automatically reload the connector whenever changes to the source code are saved.

```sh
uv run connector dev --app unitelabs.opentrons_ot2:create_app
```

## Contact

If you found a bug, please use the [issue tracker][issue-tracker].

[issue-tracker]: https://github.com/AccelerationConsortium/sila2-ot2/issues
[uv]: https://docs.astral.sh/uv/
