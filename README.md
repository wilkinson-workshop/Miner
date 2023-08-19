# Miner Development API
miner.py how-to guide

---
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

---
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

---
## Java Execution Utilities
Functions in this section interface with Java.

| **Function Name** | **Arguments**                                                                                                                         | **Description**                                                       | **Returns** |
|-------------------|---------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|-------------|
| `java_exec_jar`   | jar: `Path`<br>\*xx: `str`<br>exec_from: `Path` \| None<br>xms: `str` \| `None`<br>xmx: `str` \| `None`<br>with_gui: `bool` \| `None` | Executes a target JAR file with arguments. This function is blocking. | N/A         |

## Java JAR Management Utilities
Functions which manage JAR files we use in our Minecraft services.

#### JARs Manifest
| **Function Name** | **Arguments**                                | **Description**                                                                                                                                                                                                                                                                                        | **Returns**                          |
|-------------------|----------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------|
| `jars_cfg`        | mc: `Minecraft`                              | Get the path to the jars.toml file.                                                                                                                                                                                                                                                                    | Path to the JARs manifest.           |
| `jars_cfg_load`   | mc: `Minecraft`                              | Loads the JARs manifest.                                                                                                                                                                                                                                                                               | JARs manifest loaded as a mapping.   |
| `jars_cfg_opt`    | mc: `Minecraft`<br>name: str<br>default: Any | Perform a lookup for some value along the path given in the JARs manifest. This function throws an error if no value can be retrieved or if the path is invalid. Valid paths follow the pattern of a dot-separated string. Paths may contain a '*' character, but only if it's at the end of the path. | A mapping containing found value(s). |

#### Download Utilities
| **Function Name**      | **Arguments**                                          | **Description**                                                     | **Returns**                             |
|------------------------|--------------------------------------------------------|---------------------------------------------------------------------|-----------------------------------------|
| `jars_download`        | mc: `Minecraft`<br>jar: `JarFile`                      | Downloads a JAR file.                                               | N/A                                     |
| `jars_download_exists` | mc: `Minecraft`<br>jar: `JarFile` url: `str` \| `None` | Checks for the target JAR file in local filesystem.                 | Whether a JAR file has been downloaded. |
| `jars_jar_check`       | mc: `Minecraft`<br>jar: `JarFile`                      | Constructs a URL for a `JarFile` and test that the endpoint exists. | Whether a JAR file can be downloaded.   |
| `jars_jar_url`         | mc: `Minecraft`<br>jar: `JarFile`                      | Constructs a JAR download URL from JARs manifest.                   | Download URL for the target JAR file.   |

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

---
## Miner Command Line Interface
The below functions are explicit declarations of our CLI which interacts with
the underlying API as described by the functions found above.

`main_cli()`
Manage Aabernathy services.

`start(name: str, service: Service | None = None, mc_version: str | None = None, mem_ini: str | None = None, mem_max: str | None = None)`
Start a service.

`backup(name: str, service: Service | None = None, mc_version: str | None = None, preserve: bool | None = None)`
Create a backup of a service.

`restore(name: str, mc_version: str | None = None, tag: str | None = None, **_)`
Restore service from backup.

`jars()`
Manage JAR files.

`check(name: str, mc_version: str | None = None, build_version: str | None = None, build_id: str | None = None)`
Construct a download URI and test it with a ping to the host.

`get(name: str, mc_version: str | None = None, build_version: str | None = None, build_id: str | None = None)`
Download a single JAR file.

`getpkg(name: str, mc_version: str | None = None)`
Download a package of JAR files.
