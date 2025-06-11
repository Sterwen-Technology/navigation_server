## Using a Python virtual environment

Using a virtual environment to run Python application is highly recommended and close to mandatory in the latest Linux release.
Virtual environment can isolate the application at 2 levels:
- Running a specific Python version independently of the one installed at system level
- Install the required package for the application without impacting requirements from other applications

Installation files are available here: [Sterwen Technology download page](https://sterwen-technology.eu/softwares/)

There are many existing solutions to achieve the same results. I am proposing a configuration that have been able to fully tested and is based on 2 well known Python tools:
- **[pyenv](https://github.com/pyenv/pyenv#readme)** to install specific Python version and possibly virtual environments for execution
- **[poetry](https://python-poetry.org/)** to manage dependencies and create associated virtual environment

### pyenv installation and configuration

To install pyenv: `curl -fsSL https://pyenv.run | bash`
Then add the pyenv environment into .bashrc file (follow the instructions of the installation script) and restart your shell.

As pyenv is recompiling the python interpreter and environment locally, you need to install a bunch of development packages:

```sh
sudo apt update; sudo apt install build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev curl git \
libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
```

Install the right Python version: `pyenv install 3.12.3`. That version is the actual recommendation, but that is not a hard requirement.

If you are intending to install from a wheel, then you can create directly a virtual environment for it:
`pyenv virtualenv 3.12.3 test_navigation` is creating a virtual environment named *test_navigation*

`pyenv activate test_navigation` is activating it locally

Assuming that you have downloaded locally **navigation_server-2.2.0-py3-none-any.whl** in your local directory you directly install the application.
`pip install navigation_server-2.2.0-py3-none-any.whl`

You can then test the installation by launching `navigation_server`. This will start a server but immediately due to a lack of configuration file.

Samples can be found in [configuration samples on GitHub](https://github.com/Sterwen-Technology/navigation_server/tree/V2.1/conf)

### Installing poetry

Poetry is interesting if you want to work from the tarball or from sources as it allows to manage dependencies without pushing the code in specific directories.

**Note: The application requires poetry 2.0.0 and over**.
The right Python version must be installed first. If you use the Python version installed by pyenv use
```shell
pyenv global 3.12.3
```

Installation is straightforward: 
```shell
curl -sSL https://install.python-poetry.org | python -
```

### Installation from a tarball or from source

In both cases the whole application will be installed in a single subdirectory from the local one.

```shell
tar xvzf navigation_server-2.2.0.tar.gz
```

or

```shell
git clone https://github.com/Sterwen-Technology/navigation_server.git
```

Will bring you the necessary code locally.
If you don't want to modify the source and/or to have to bother with git, you can stick with the tarball.

To manage dependencies, **poetry** is to be used.
```shell
cd navigation_server
poetry install --all-extras
poetry run ./setrunenv
```
*setrunenv* stores in the local directory the reference to the virtual environment created by **poetry**.

In case of upgrade for a new release on the same system, here is the usual procedure:
```shell
tar xvf navigation_server-V2.5.1
rm navigation_server
ln -s navigation_server-V2.5.1 navigation_server
cd navigation_server
poetry sync --all-extras
poetry run ./setrunenv
```

To launch a server just use: `./run_server <configuration file>`

Data samples to simulate a NMEA2000 network are available on Sterwen-Technology website.

### System-wide installation

It is always possible to set up the system without virtual environment. This shall be reserved for embedded systems where upgrade are made using full image replacement.

Here are the steps to be followed to perform that installation:
1. Install the target Python version using apt
2. Extract the tar in the target directory
3. Install all the needed packages (listed in the **project.toml** file) using apt

## Running the server in a virtual environment

Virtual environments are local and context dependents. So it is hard to run a Python program with its dependencies in any context on the system.
In particular for functions that require superuser privilege or that are launched from systemd. The paragraph covers only the case where the system has been installed from **tar** and dependencies setup via **poetry**.

To overcome that problem, a convenience script has been developed: **run_server**. That script can be called from any context and is launching the *navigation_server/server_main.py* with the correct environment.
To have this script running properly ```poetry run ./setrunenv``` must have executed after the installation of the dependencies.

Usage: 
```shell
run_server <configuration file>
```

'<configuration file>' can be found in 2 ways:

- The file path is existing, then the file is used right away
- The file path is not existing, then the "conf" path is added to the NAVIGATION_HOME environment variable or the directory of the **run_server** script itself.

Examples:

Assuming that the navigation_server has been installed in */home/acme/nav*

running locally: 
```shell
cd /home/acme/nav; run_server log_simulator.yml
```
That is running the server with the configuration file */home/acme/nav/conf/log_simulator.yml*

running the server from systemd, here is the execution line in the service file

```unit file (systemd)
ExecStart=/data/solidsense/navigation/run_server /data/solidsense/config/energy_management.yml
```




