# Miner
A Minecraft server utility CLI.

The Aaberanthy Development Team uses this Python script to manage its services and subsequent plugins. It comes with a small suite of commands at the user's disposal.
Before running this script, you will need to install some dependencies into your environment:
```bash
$ pip3 install click, httpx, jproperties, wget
```

Afterwards, you should be able to run the file as-is, like so:
```bash
$ bin/miner.py --help
Usage: miner.py [OPTIONS] COMMAND [ARGS]...

  Manage Aabernathy services.

Options:
  --help  Show this message and exit.

Commands:
  backup   Create a backup of a service.
  jars     Manage JAR files.
  restore  Restore service from backup.
  start    Start a service.
```

`backup`, `restore` and `start` directly affect files and assets on a target service. `jars` works by managing plugin downloads defined in the JARs manifest located in `jars/jars.toml`

If your first attempt to run the script does not work, be sure to modify the shebang statement at the top of `bin/miner.py`:
```python
#!/opt/minecraft/.venv/bin/python
...
```

Or run the script directly from your Python of choice:
```bash
$ python3 bin/miner.py --help
```

# Miner Development API
A `miner.py` how-to guide. Sections below this point describe the underlying API. These objects and functions dictate the features Miner has to offer.

## Common Objects
Objects, types and other defintinions used commonly between API sections.

**JarFile(\*args, \*\*kwds)**
JAR file common variables.

**JarPackage(\*args, \*\*kwds)**
Collection Jar files and additional metadata.

**Minecraft(\*args, \*\*kwds)**
Minecraft common variables.

**Service**
Type of service for minecraft.
* `Paper` A server JAR instance.
* `Velocity` A proxy JAR instance.
* `Plugin` A plugin JAR instance.

**Version(\*args)**
Version representation.

## Common Utilities
Tools in this section describe common use utilites shared between other facets in this API.

#### File System Utilities
| **Function Name**      | **Arguments**                                      | **Description**                                                                                                                                  | **Returns**                                                               |
|------------------------|----------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| `archive_name`         | mc: `Minecraft`<br>idn: `str` \| `None`            | Create archive name.                                                                                                                             | A string representing a file name.                                        |
| `archive_name_stamp`   | N/A                                                | Create a default archive name stamp.                                                                                                             | A string representing a datetime in hexidecimal form.                     |
| `archive_read`         | mc: `Minecraft`<br>idn: `str` \| `None`            | Open a service archive for reading.                                                                                                              | A zipfile context manager open for reading.                               |
| `archive_write`        | mc: `Minecraft`<br>preserve: `bool` \| `None`      | Open a service archive for writing. If `preserve` is `True`, and the archive target exists, rename the existing target and create a new archive. | A zipfile context manager open for writing.                               |
| `from_directory`       | path: `Path`                                       | Change the current working directory to the given path.                                                                                          | A non-return context manager which changes the current working directory. |
| `make_jarname`         | mc: `Minecraft`<br>service: `Service`              | Returns a concatenated version of the passed values as a JAR path.                                                                               | A path to a JAR file.                                                     |
| `which`                | name: `str`                                        | Locate some binary on `PATH`.                                                                                                                    | All executable paths that match.                                          |

#### Service Utilities
| **Function Name**      | **Arguments**                                      | **Description**                                                                                                                                  | **Returns**                                                               |
|------------------------|----------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| `service_arch_include` | mc: `Minecraft`<br>service: `Service`              | Get the include file list for files to be archived.                                                                                              | A sequence of paths to be archived for a service.                         |
| `service_new`          | service: `str` \| `int` \| `Service` \| `None`     | Create a services instance.                                                                                                                      | An instance of `Service` enumeration.                                     |
| `service_opt_apply`    | fn: `Callable`<br>opts: `Sequence[Callable]`       | Wraps the given function with the opts.                                                                                                          | A wrapped instance of the function applying callable options.             |
| `service_opts_common`  | fn: `Callable`                                     | Wrap function with common CLI options.                                                                                                           | A wrapped instance of the function as a Command.                          |
| `service_opts_java`    | fn: `Callable`                                     | Wrap function with common Java options.                                                                                                          | A wrapped instance of the function as a Command.                          |

#### Miscellaneous
| **Function Name**      | **Arguments**                                      | **Description**                                                                                                                                  | **Returns**                                                               |
|------------------------|----------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| `snake2camel`          | s: `str`                                           | Transform a snake-case string into a camel-cased string.                                                                                         | A camel-cased string.                                                     |
| `version_new`          | version: `str` \| `tuple` \| `Version` \| `None`   | Create a version instance.                                                                                                                       | An instance of `Version`.                                                 |

## Java Execution Utilities
Functions in this section interface with Java.

| **Function Name** | **Arguments**                                                                                                                         | **Description**                                                       | **Returns** |
|-------------------|---------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|-------------|
| `java_exec_jar`   | jar: `Path`<br>\*xx: `str`<br>exec_from: `Path` \| None<br>xms: `str` \| `None`<br>xmx: `str` \| `None`<br>with_gui: `bool` \| `None` | Executes a target JAR file with arguments. This function is blocking. | N/A         |

## Java JAR Management Utilities
Functions which manage JAR files we use in our Minecraft services.

#### JARs Manifest
| **Function Name** | **Arguments**                                    | **Description**                                                                                                                                                                                                                                                                                        | **Returns**                              |
|-------------------|--------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------|
| `jars_cfg`        | mc: `Minecraft`                                  | Get the path to the jars.toml file.                                                                                                                                                                                                                                                                    | Path to the JARs manifest.               |
| `jars_cfg_ispkg`  | cfg: `Mapping`<br>name: `str`                    | Determine if a mapping qualifies as a package configuration                                                                                                                                                                                                                                            | Whether a map is a package config or not |
| `jars_cfg_load`   | mc: `Minecraft`                                  | Loads the JARs manifest.                                                                                                                                                                                                                                                                               | JARs manifest loaded as a mapping.       |
| `jars_cfg_opt`    | mc: `Minecraft`<br>name: `str`<br>default: `Any` | Perform a lookup for some value along the path given in the JARs manifest. This function throws an error if no value can be retrieved or if the path is invalid. Valid paths follow the pattern of a dot-separated string. Paths may contain a '*' character, but only if it's at the end of the path. | A mapping containing found value(s).     |

#### Download Utilities
| **Function Name**       | **Arguments**                                          | **Description**                                                     | **Returns**                             |
|-------------------------|--------------------------------------------------------|---------------------------------------------------------------------|-----------------------------------------|
| `jars_download`         | mc: `Minecraft`<br>jar: `JarFile`                      | Downloads a JAR file.                                               | N/A                                     |
| `jars_download_package` | mc: `Minecraft`                                        | Downloads a package of JAR files                                    | N/A                                     |
| `jars_download_exists`  | mc: `Minecraft`<br>jar: `JarFile` url: `str` \| `None` | Checks for the target JAR file in local filesystem.                 | Whether a JAR file has been downloaded. |
| `jars_jar_check`        | mc: `Minecraft`<br>jar: `JarFile`                      | Constructs a URL for a `JarFile` and test that the endpoint exists. | Whether a JAR file can be downloaded.   |
| `jars_jar_url`          | mc: `Minecraft`<br>jar: `JarFile`                      | Constructs a JAR download URL from JARs manifest.                   | Download URL for the target JAR file.   |
| `jars_link`             | mc: `Minecraft`<br>jar: `JarFile`                      | Link a `JarFile` to its destination service.                        | N/A                                     |
| `jars_link_package`     | mc: `Minecraft`                                        | Link a package of `JarFile`s to their destination service.          | N/A                                     |         

#### JAR File Attributes
| **Function Name**     | **Arguments**                                                                                  | **Description**                                                      | **Returns**                                 |
|-----------------------|------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|---------------------------------------------|
| `jars_jar_definition` | mc: `Minecraft`<br>jar: `JarFile`<br>default: `Any` \| `None`                                  | Get the URI definition, or definitions, associated with a `JarFile`. | Mapping of JAR name to pre-formated URI(s). |
| `jars_jar_host`       | mc: `Minecraft`<br>jar: `JarFile`<br>default: `Any` \| `None`                                  | Get the host, or hosts, associated with a `JarFile`.                 | Mapping of JAR name to hostname(s).         |
| `jars_jar_name`       | mc: `Minecraft`<br>jar: `JarFile`                                                              | Get the name, or names, associated with a `JarFile`.                 | Mapping of JAR name to file name(s).        |
| `jars_jar_package`    | mc: `Minecraft`<br>jar: `JarFile`                                                              | Get the package, or packages, associated with a `JarFile`.           | Mapping of JAR name to `JarPackage`(s).     |

#### JAR Object Construction
| **Function Name**  | **Arguments**                                                                                                            | **Description**                                                      | **Returns**                                 |
|--------------------|--------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|---------------------------------------------|
| `jars_jar_new`     | name: `str`<br>version: `str` \| `Version` \| `tuple`<br>build: `str` \| `None`<br>service: `str` \| `Service` \| `None` | Create a JAR file instance.                                          | A new `JarFile` instance.                   |
| `jars_package_new` | mc: `Minecraft`<br>name: `str`<br>from_packages: `str` \| `JarPackage` \| `Sequence` \| `None`                           | Create a package instance.                                           | A new `JarPackage` instance.                | 
---
## Minecraft Specific Utilities
Manage Minecraft services by starting, archiving, backup restoration and etc.

#### Archive Services
| **Function Name**          | **Arguments**                                                       | **Description**                 | **Returns** |
|----------------------------|---------------------------------------------------------------------|---------------------------------|-------------|
| `minecraft_server_archive` | mc: `Minecraft`<br>service: `Service`<br>preserve: `bool` \| `None` | Archive the target service.     | N/A         |
| `minecraft_server_restore` | mc: `Minecraft`<br>idn: `str` \| `None`                             | Restore a service from archive. | N/A         |

#### Start Services
| **Function Name**            | **Arguments**                                                                         | **Description**                            | **Returns** |
|------------------------------|---------------------------------------------------------------------------------------|--------------------------------------------|-------------|
| `minecraft_server_pxy_start` | mc: `Minecraft`<br>xms: `str` \| `None`<br>xmx: `str` \| `None`                       | Starts a single Minecraft proxy server.    | N/A         |
| `minecraft_server_svr_start` | mc: `Minecraft`<br>xms: `str` \| `None`<br>xmx: `str` \| `None`                       | Starts a single Minecraft server.          | N/A         |
| `minecraft_service_start`    | mc: `Minecraft`<br>service: `Service`<br>xms: `str` \| `None`<br>xmx: `str` \| `None` | Starts an instance of a Minecraft service. | N/A         |

**Notice**: These parameters might need some explaining.
`xms`: Initial heap size.
`xmx`: Maximum heap size.

#### Miscellaneous
| **Function Name**       | **Arguments**                                                                                                                                                                                                                                                                                                               | **Description**                        | **Returns**                 |
|-------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------|-----------------------------|
| `minecraft_new`         | name: `str`<br>version: `str` \| `Version` \| `tuple`<br>pxy_build: `int` \| `None`<br>pxy_version: `str` \| `Version` \| `tuple` \| `None`<br>svr_build: `int` \| `None`<br>svr_version: `str` \| `Version` \| `tuple` \| `None`<br>bak_root: `Path` \| `None`<br>exe_root: `Path` \| `None`<br>jar_root: `Path` \| `None` | Create a new Minecraft instance.       | A new `Minecraft` instance. |
| `minecraft_server_init` | mc: `Minecraft`                                                                                                                                                                                                                                                                                                             | Initializes a single Minecraft server. | N/A                         |
