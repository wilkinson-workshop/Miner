#!/opt/minecraft/.venv/bin/python3
"""
miner.py
-------------------
Keenan W. Wilkinson
16 Aug 2023
-------------------
Basic CLI for maintaining server services.
"""

import contextlib
import datetime
import enum
import os
import pathlib
import re
import subprocess
import tomllib
import typing
import zipfile

import click, httpx, jproperties, wget

# -----------------------------------------------
# Common script objects.
# -----------------------------------------------

T = typing.TypeVar("T")
JarConfResponse = typing.Mapping[str, T]
Unset = type("Unset", (int,), {})
Version  = None
VersionT = str | tuple[str | int, ...] | Version

REGEX_CAMEL_CASE        = re.compile(r"([A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$)))|_")
REGEX_FMT_ARG_SPECIFIER = lambda arg: (re.compile(r"\{%s\}" % (arg,)))
REGEX_FMT_KWD_SPECIFIER = lambda kwd: (re.compile(r"\{%s:[\w\-_]+\}" % (kwd,)))


# JarFile(build: str | int, name: str, version: Version)
class JarFile(typing.NamedTuple):
    """JAR file common variables."""

    build:   str | int
    name:    str
    version: "Version"
    service: "Service"

    def __str__(self):
        sub = f"{self.version}"
        if self.build:
            sub = f"version={self.version!r} build={self.build!r}"
        return f"JarFile[{self.name}:{self.service}]({sub})"

# JarPackage(name: str, from_packages: JarPackage, depends: Sequence[JarPackage])
class JarPackage(typing.NamedTuple):
    """
    Collection Jar files and additional metadata.
    """

    name:          str
    from_packages: str | typing.Self | typing.Sequence[typing.Self] | None
    depends:       typing.Sequence[JarFile] | None


class Minecraft(typing.NamedTuple):
    """Minecraft common variables."""

    bak_root: pathlib.Path

    exe_root: pathlib.Path
    exe_name: str

    jar_root:     pathlib.Path
    jar_pxy_bld:  int
    jar_pxy_ver: "Version"
    jar_svr_bld:  str
    jar_svr_ver: "Version"

    pkg_name: str

    version: "Version"


class Service(enum.StrEnum):
    """Type of service for Minecraft."""

    Paper    = enum.auto()
    Velocity = enum.auto()
    Plugin   = enum.auto()


class Version(typing.NamedTuple):
    """Version representation."""

    major: int
    minor: int
    patch: int | str

    def __iter__(self) -> typing.Iterator[int | str]:
        return iter((self.major, self.minor, self.patch))

    def __str__(self) -> str:
        return ".".join((str(i) for i in self))

    def __bool__(self) -> bool:
        return all(
            map(lambda p: p >= 0 if isinstance(p, int) else bool(p), self))


# -----------------------------------------------
# Common script utilities.
# -----------------------------------------------

def archive_name(mc: Minecraft, idn: str | None = None):
    """Create archive name."""

    idn = idn or archive_name_stamp()
    return f"{mc.exe_name}-{mc.version!s}-{idn}.bak.zip"

def archive_name_stamp():
    """Create a default archive name stamp."""

    dt = datetime.datetime.now()
    st = (
        str(dt.year)[-2:],
        str(dt.isocalendar()[1]).rjust(2, "0"),
        str(dt.weekday()).rjust(2, "0"),
    )
    return f"{hex(int(''.join(st)))}-{dt.hour:02}"


@contextlib.contextmanager
def archive_read(
    mc: Minecraft,
    idn: str | None = None) -> typing.Generator[zipfile.ZipFile, None, None]:
    """Open a service archive for reading."""

    name = archive_name(mc, idn or "0")
    bak  = (mc.bak_root / name)
    zf   = zipfile.ZipFile(bak, mode="r")
    try:
        yield zf
    finally:
        zf.close()


@contextlib.contextmanager
def archive_write(
    mc: Minecraft,
    preserve: bool | None = None) -> typing.Generator[zipfile.ZipFile, None, None]:
    """Open a service archive for writing."""

    bak = (mc.bak_root / archive_name(mc, "0"))
    if bak.exists() and preserve:
        bak.rename(bak.parent / archive_name(mc))

    zf = zipfile.ZipFile(bak, mode="w")
    try:
        yield zf
    finally:
        zf.close()


@contextlib.contextmanager
def from_directory(path: pathlib.Path):
    """
    Perform some operation from the given
    directory.
    """

    origin = pathlib.Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(origin)


def make_jarname(mc: Minecraft, service: Service) -> pathlib.Path:
    """
    Returns a concatentated version of the passed
    values as jar path.
    """

    root  = (mc.jar_root / str(mc.version))
    name  = str(service)
    parts = ["*", "*"]

    if service is Service.Paper:
        parts[0] = str(mc.jar_svr_ver)
        if int(mc.jar_svr_bld) >= 0:
            parts[1] = str(mc.jar_svr_bld)

    elif service is Service.Velocity:
        if mc.jar_pxy_ver.major >= 0:
            parts[0] = str(mc.jar_pxy_ver)
        if mc.jar_pxy_bld >= 0:
            parts[1] = str(mc.jar_pxy_bld)

    name = "-".join((name, *parts)) + ".jar"
    if "*" in name:
        # Find the first available build.
        return next(root.rglob(name))

    return (root / name)


def service_arch_include(
    mc: Minecraft,
    service: Service) -> tuple[pathlib.Path, ...]:
    """Gets the include file list."""

    exe_from = (mc.exe_root / mc.exe_name)
    include  = ()

    # Define what files we want to preserve
    # in our backup.
    if service is Service.Paper:
        config = jproperties.Properties()
        config.load((exe_from / "server.properties").read_text())
        include = (
            exe_from / "server.properties",
            exe_from / "config",
            exe_from / "bukkit.yml",
            exe_from / "spigot.yml",
            exe_from / "usercache.json"
        )

        include += tuple(exe_from.glob(f"{config['level-name'].data}*"))

    return include


def service_new(service: str | int | Service | None = None) -> Service:
    """Return a services instance."""

    if not service:
        return Service.Paper
    if isinstance(service, int):
        return Service(service) #type: ignore
    if isinstance(service, str):
        return Service[snake2camel(service)]

    raise TypeError(f"Unsupported conversion from {service!r} to {Service}")


def service_opts_apply(
    fn: typing.Callable,
    opts: typing.Sequence[typing.Callable]) -> typing.Callable:
    """Wrap function with CLI options."""

    for o in opts:
        fn = o(fn)
    return fn


def service_opts_common(fn: typing.Callable) -> typing.Callable:
    """Wrap function with common CLI options."""

    opts = (
        click.argument("name"),
        click.option("-s", "--service", default="paper"),
        click.option("-V", "--mc-version", default="1.20.1"))
    return service_opts_apply(fn, opts)


def service_opts_java(fn: typing.Callable) -> typing.Callable:
    """Wrap function with common Java options."""

    opts = (
        click.option("-m", "--mem-ini"),
        click.option("-M", "--mem-max"))
    return service_opts_apply(fn, opts)


def snake2camel(s: str) -> str:
    """
    Transform a lsnake-case string into a
    camel-cased string.
    """

    return "".join([
        i.capitalize()
        for i in filter((lambda s: bool(s)), REGEX_CAMEL_CASE.split(s))
    ])


def version_new(
    version: VersionT | None = None) -> Version:
    """Create a new `Version` instance."""

    if not version:
        return Version(-1, 0, 0)
    if isinstance(version, Version):
        return version
    if isinstance(version, str):
        version = [int(i) if i.isnumeric() else i for i in version.split(".")] #type: ignore
        if len(version) != 3:
            return ".".join(map(str, version))
    if isinstance(version, typing.Iterable):
        return Version(*version) #type: ignore

    raise TypeError(f"Unsupported conversion from {version!r} to {Version}")


def which(name: str) -> typing.Generator[pathlib.Path, None, None]:
    """
    Locate some binary on PATH. Returns all
    executable paths.
    """

    paths = map(pathlib.Path, os.environ["PATH"].split(":"))
    found = []

    for p in paths:
        found.extend(p.rglob(name))

    return (f for f in found if os.access(str(f), os.X_OK))


# -----------------------------------------------
# Java execution utilities.
# -----------------------------------------------

def java_exec_jar(
    jar: pathlib.Path,
    *xx: str,
    exec_from: pathlib.Path | None = None,
    xms: str | None = None,
    xmx: str | None = None,
    with_gui: bool | None = None) -> None:
    """Execute a target jar file with args."""

    exec_as   = next(which("java"))
    exec_from = exec_from or pathlib.Path.cwd()
    exec_opts = tuple((f"-XX:{x}" for x in xx))
    exec_xms  = "-Xms" + (xms or "1G")
    exec_xmx  = "-Xmx" + (xmx or "1G")

    exec_args = (
        (str(exec_as), exec_xms, exec_xmx)
        + exec_opts
        + ("-jar", str(jar)))

    if with_gui is not None and not with_gui:
        exec_args += ("--nogui",)

    with from_directory(exec_from):
        subprocess.call(exec_args, start_new_session=True)


# -----------------------------------------------
# Java Jar management utilities.
# -----------------------------------------------

def jars_cfg(mc: Minecraft) -> pathlib.Path:
    """Gets the jars configuration path."""

    return (mc.jar_root / "jars.toml")


def jars_cfg_load(mc: Minecraft) -> typing.Mapping:
    """Loads the jars configuration."""

    return tomllib.loads(jars_cfg(mc).read_text())


def jars_cfg_opt(
    mc: Minecraft,
    name: str,
    default: T | None = Unset) -> JarConfResponse:
    """
    Perform a lookup of some value in the jars
    config.
    """

    parts  = name.split(".")
    config = jars_cfg_load(mc)

    for idx, part in enumerate(parts):
        # If the last path part contains a star,
        # do a regex lookup of all keys in the
        # map.
        if part is parts[-1] and "*" in part:
            part = re.compile(part.replace("*", r".*"))
            return {k:v for k,v in config.items() if part.match(k)}

        # Reverse lookup if no matching names are
        # found. This is a last-ditch effort.
        if part is parts[-1] and part not in config:
            temp = tuple(filter(lambda k: part.find(k) != -1, config.keys()))
            if len(temp) >= 1:
                part = sorted(temp, reverse=True)[0]

        # If the current path part can't be found
        # in the current map, bail on the loop.
        if part not in config:
            config = Unset
            break
        config = config[part]

    # If no default is provided, and the lookup
    # failed, panic.
    if config is Unset and default is Unset:
        raise KeyError(f"{part!r} does not exist in {'.'.join(parts[:idx])!r}")

    if config is Unset:
        return default

    # Take advantage of leaked variable in local
    # space.
    return {part: config}


def jars_download(mc: Minecraft, jar: JarFile) -> None:
    """Downloads a JAR file."""

    urls = jars_jar_url(mc, jar)
    dst  = mc.jar_root / str(mc.version)

    dst.mkdir(exist_ok=True)
    for name, url in urls.items():
        # Check first if JAR has been downloaded
        # already.
        if jars_download_exists(mc, jar, url):
            click.echo(f"{jar} already installed for version {mc.version}")
            continue

        wget.download(url, str(dst))
        # Progress bar for wget.download does not
        # print a new line on its own.
        click.echo("\n")

        # Check that url name and JAR name match
        # if JAR name exists in jars config.
        url_name = wget.detect_filename(url)
        jar_name = jars_jar_name(mc, jar, {}).get(name, "notfound")
        if jar_name == "notfound":
            continue
        if url_name != jar_name:
            (dst / url_name).rename((dst / jar_name))


def jars_download_exists(
    mc: Minecraft,
    jar: JarFile,
    url: str | None = None) -> bool:
    """Whether a JAR file has been downloaded."""

    def isinvalid_count(v):
        return not isinstance(v, str) and len(v) > 1 and ("*" not in jar.name)

    dst = mc.jar_root / str(mc.version)
    url = url or jars_jar_url(mc, jar)
    if isinvalid_count(url):
        raise TypeError(f"Found multiple urls associated with {jar}.")
    if isinstance(url, typing.Mapping):
        url = url[jar.name]

    name = jars_jar_name(mc, jar, {})
    if isinvalid_count(name):
        raise TypeError(f"Found multiple names associated with {jar}.")
    name = name.get(jar.name, "notfound")

    paths = (
        (dst / wget.detect_filename(url)),
        (dst / name)
    )

    return any(map(lambda p: p.exists(), paths))


def jars_download_package(mc: Minecraft, jar: JarFile):
    """Downloads JAR files from target package."""

    pkgs = jars_jar_package(mc, jar)
    for name, pkg in pkgs.items():
        click.echo(f"found package {name}")
        for j in pkg.depends:
            jars_download(mc, j)


def jars_jar_check(mc: Minecraft, jar: JarFile) -> bool:
    """
    Build URL from `JarFile` and test that it exists.
    """

    urls = jars_jar_url(mc, jar)
    for name, url in urls.items():
        r = httpx.head(url, follow_redirects=True)
        click.echo(f"{name}: {url} {r.status_code}")

    return r.status_code in range(200, 300)


def jars_jar_definition(mc: Minecraft, jar: JarFile) -> JarConfResponse[str]:
    """
    Get the URI definition, or definitions,
    associated with this `JarFile`.
    """

    return jars_cfg_opt(mc, f"jars.uri.definitions.{jar.name}")


def jars_jar_host(
    mc: Minecraft,
    jar: JarFile,
    default: T | Unset = Unset) -> JarConfResponse[T]:
    """
    Get the host, or hosts, associated with this
    `JarFile`.
    """

    return jars_cfg_opt(mc, f"jars.uri.special.hosts.{jar.name}", default)


def jars_jar_name(
    mc: Minecraft,
    jar: JarFile,
    default: T | Unset = Unset) -> JarConfResponse[T]:
    """
    Get the name, or names, associated with this
    `JarFile`.
    """

    return jars_cfg_opt(mc, f"jars.uri.special.names.{jar.name}", default)


def jars_jar_new(
    name: str,
    version: VersionT | None = None,
    build:  str | int | None = None,
    service: Service | str | None = None) -> JarFile:
    """Constructs new `JarFile`. representation."""

    build   = str(build) if build else ""
    version = version_new(version)
    service = service or Service.Plugin
    return JarFile(build, name, version, service)


def jars_jar_package(
    mc: Minecraft,
    jar: JarFile) -> JarConfResponse[JarPackage]:
    """
    Get the package, or packages, associated with
    this `JarFile`.
    """

    def inner(packages, pkg_name=None):
        for name, pkg in packages.items():
            # Sometimes we are parsing a subpackage
            # from a parent package.
            if name in ("from_packages", "depends"):
                continue

            pkg["from_packages"] = pkg.pop("from", None)
            pkg["depends"] = pkg.pop("depends", None)

            if pkg_name:
                name = ".".join([pkg_name, name])
            ret[name] = jars_package_new(mc, name, **pkg)

    ret = {}
    pkg_path = ("jars", "packages", jar.name)
    if jar.version:
        pkg_path += (str(jar.version).replace(".", "_"),)
    pkg_path = ".".join(pkg_path)
    pkgs     = jars_cfg_opt(mc, pkg_path)

    try:
        inner(pkgs)
    except TypeError:
        # Parsing failed. Most likely a super
        # package.
        for name, sub_pkgs in pkgs.items():
            inner(sub_pkgs, name)

    return ret


def jars_jar_url(mc: Minecraft, jar: JarFile) -> JarConfResponse[str]:
    """
    Constructs a JAR download URL from
    configuration.
    """

    jars = [jar]
    if "*" in jar.name:
        jars = jars_jar_name(mc, jar, {})
        jars = [jars_jar_new(n, jar.version, jar.build) for n in jars]
        return {j.name:jars_jar_url(mc, j)[j.name] for j in jars}

    def getvar(kwd):
        reg = REGEX_FMT_KWD_SPECIFIER(kwd)
        return reg.findall(url)[0].strip("}{").split(":", 2)[1]

    def isunset(arg):
        reg = REGEX_FMT_ARG_SPECIFIER(arg)
        return arg not in params and len(reg.findall(url))

    def isunsetvar(kwd):
        reg = REGEX_FMT_KWD_SPECIFIER(kwd)
        return kwd not in params and len(reg.findall(url))

    def mapget(m):
        return m.get(jar.name, tuple(m.values())[0])

    def panic(kwd):
        click.echo(f"{jar.name}: {kwd!r} is required to build URL.", err=True)
        quit(1)

    def replvar(kwd):
        reg = REGEX_FMT_KWD_SPECIFIER(kwd)
        return reg.subn("{" + kwd + "}", url, 1)[0]

    # There's a possibility of the reverse lookup
    # to produce multiple, one or no definitions.
    definitions = jars_jar_definition(mc, jar)
    params      = dict()
    url         = mapget(definitions)
    while re.findall(r"\{.*\}", url):
        if isunset("build"):
            if not jar.build:
                panic("build")
            params["build"] = str(jar.build)

        if isunset("host"):
            host = jars_jar_host(mc, jar, {})
            if not host:
                panic("host")
            params["host"] = mapget(host)

        if isunsetvar("host"):
            host = getvar("host")
            host = jars_cfg_opt(mc, f"jars.uri.special.hosts.{host}", {})
            if not host:
                panic(host)
            params["host"] = mapget(host)
            url = replvar("host")

        if isunset("name"):
            spec_name = jars_jar_name(mc, jar, {})
            if not spec_name:
                click.echo(f"'name' is required to build URL.")
                quit(1)
            params["name"] = spec_name[jar.name]

        if isunset("version"):
            if not (jar.version or mc.version):
                click.echo(f"'version' is required to build URL.", err=True)
                quit(1)
            params["version"] = version_new(jar.version or mc.version)

        url = url.format_map(params)

    return {jar.name: url}


def jars_package_new(
    mc: Minecraft,
    name: str,
    from_packages: str | JarPackage | typing.Sequence[str | JarPackage] | None = None,
    depends: typing.Sequence[JarFile] | None = None) -> JarPackage:
    """Create a new `JarPackage` instance."""

    def from_pkgs(pkgs, cls=None):

        def panic(kwd):
            click.echo(
                f"{name} {kwd!r} is required to build package.", err=True)
            quit(1)

        for idx, pkg in enumerate(pkgs):
            if isinstance(pkg, cls):
                continue

            if isinstance(pkg, str):
                name = pkg
                pkg  = jars_cfg_opt(mc, pkg)[name.rsplit(".", 1)[-1]]
                pkg["name"] = name

            if not isinstance(pkg, typing.Mapping):
                msg = f"Unsupported conversion from {pkg!r} to {cls}"
                raise TypeError(msg)

            if "name" not in pkg:
                panic("name")

            if cls is JarPackage:
                pkg = jars_package_new(
                    mc,
                    pkg["name"],
                    pkg.get("from", None),
                    pkg.get("depends", None))
            elif cls is JarFile:
                pkg = jars_jar_new(**pkg)

            pkgs[idx] = pkg

        return tuple(pkgs)

    if depends:
        depends = from_pkgs(depends, JarFile)

    if isinstance(from_packages, (str, JarPackage)):
        from_packages = [from_packages]
    if from_packages:
        from_packages = from_pkgs(from_packages, JarPackage)

    if not from_packages:
        return JarPackage(name, from_packages or None, depends)

    depends = depends or []
    for pkg in from_packages:
        depends.extend(pkg.depends or [])

    return JarPackage(name, from_packages or None, tuple(depends))

# -----------------------------------------------
# Minecraft specific utilities. Used for
# executing and organizing services.
# -----------------------------------------------

def minecraft_new(
    name: str,
    version: VersionT,
    pkg_name: str | None = None,
    *,
    pxy_build: int | None = None,
    pxy_version: VersionT | None = None,
    svr_build: int | None = None,
    svr_version: VersionT | None = None,
    bak_root: pathlib.Path | None = None,
    exe_root: pathlib.Path | None = None,
    jar_root: pathlib.Path | None = None) -> Minecraft:
    """Create new `Minecraft` args instance."""

    pxy_build = pxy_build or -1
    svr_build = svr_build or -1
    pxy_version = version_new(pxy_version)
    svr_version = version_new(svr_version or version)

    cwd = pathlib.Path.cwd()
    bak_root = bak_root or cwd / "bak"
    exe_root = exe_root or cwd / "servers"
    jar_root = jar_root or cwd / "jars"

    version = version_new(version)
    pkg_name = pkg_name or ""

    return Minecraft(
        bak_root,
        exe_root,
        name,
        jar_root,
        pxy_build,
        pxy_version,
        svr_build,
        svr_version,
        pkg_name,
        version)


def minecraft_server_archive(
        mc: Minecraft,
        service: Service,
        preserve: bool | None = None):
    """Archive the target service."""

    exe_from = (mc.exe_root / mc.exe_name)
    with archive_write(mc, preserve) as bak:
        include = service_arch_include(mc, service)

        for root, _, fls in os.walk(exe_from):
            root = pathlib.Path(root)

            if root == exe_from:
                for f in include:
                    bak.write(f) if f.is_file() else None
                continue

            is_child = any([parent in include for parent in root.parents])
            if not (is_child or (root in include)):
                continue

            for f in fls:
                f = (root / f)
                bak.write(f) if f.is_file() else None


def minecraft_server_init(mc: Minecraft):
    """Initializes a single minecraft server."""

    # Create directory if it does not exist.
    (mc.exe_root / mc.exe_name).mkdir(exist_ok=True)


def minecraft_server_restore(
    mc: Minecraft,
    idn: str | None = None):
    """Restore a service from archive."""

    with contextlib.ExitStack() as es:
        bak = es.enter_context(archive_read(mc, idn))
        cwd = pathlib.Path.cwd()

        for f in bak.filelist:
            # This should produce a full path.
            fp = (pathlib.Path(f.filename
                # Remove the F#%@ing CWD from
                # file name.
                .removeprefix(str(cwd).strip(r"\/"))
                # Remove leading & trailing
                # slashes.
                .strip(r"\/"))
                # Resolve to absolute path.
                .resolve())

            # Files should only extract back from
            # whence they came from.
            bak.extract(f, fp.parents[-1])


def minecraft_server_pxy_start(
    mc: Minecraft,
    xms: str | None = None,
    xmx: str | None = None):
    """
    Starts a single Minecraft proxy server.

    ---
    `xms`: Initial heap size.

    `xmx`: Maximum heap size.
    """

    jar = make_jarname(mc, Service.Velocity)
    xx  = (
        "+UseG1GC",
        "G1HeapRegionSize=4M",
        "+UnlockExperimentalVMOptions",
        "+ParallelRefProcEnabled",
        "+AlwaysPreTouch",
        "MaxInlineLevel=15")

    java_exec_jar(
        jar,
        *xx,
        xms=xms,
        xmx=xmx,
        exec_from=(mc.exe_root / mc.exe_name))


def minecraft_server_svr_start(
    mc: Minecraft,
    xms: str | None = None,
    xmx: str | None = None):
    """
    Starts a single Minecraft server.

    ---
    `xms`: Initial heap size.

    `xmx`: Maximum heap size.
    """

    java_exec_jar(
        make_jarname(mc, Service.Paper),
        exec_from=(mc.exe_root / mc.exe_name),
        xms=xms,
        xmx=xmx,
        with_gui=False)


def minecraft_service_start(
    mc: Minecraft,
    service: Service,
    xms: str | None = None,
    xmx: str | None = None):
    """
    Starts a single Minecraft server.

    ---
    `xms`: Initial heap size.

    `xmx`: Maximum heap size.
    """

    if service is Service.Velocity:
        minecraft_server_pxy_start(mc, xms, xmx)
    if service is Service.Paper:
        minecraft_server_svr_start(mc, xms, xmx)


# -----------------------------------------------
# Miner Command Line Interface.
# -----------------------------------------------


@click.group()
def main_cli():
    """Manage Aabernathy services."""


@main_cli.command()
@service_opts_common
@service_opts_java
def start(
    name: str,
    service: Service | None = None,
    mc_version: str | None = None,
    mem_ini: str | None = None,
    mem_max: str | None = None):
    """Start a service."""

    service = service_new(service)
    mc = minecraft_new(name, version_new(mc_version))

    minecraft_server_init(mc)
    minecraft_service_start(mc, service, mem_ini, mem_max)


@main_cli.command()
@service_opts_common
@click.option("--preserve", is_flag=True)
def backup(
    name: str,
    service: Service | None = None,
    mc_version: str | None = None,
    preserve: bool | None = None):
    """Create a backup of a service."""

    service = service_new(service)
    mc = minecraft_new(name, version_new(mc_version))
    minecraft_server_archive(mc, service, preserve)


@main_cli.command()
@service_opts_common
@click.option("-t", "--tag")
def restore(
    name: str,
    mc_version: str | None = None,
    tag: str | None = None,
    **_):
    """Restore service from backup."""

    mc = minecraft_new(name, version_new(mc_version))
    minecraft_server_restore(mc, tag)


@main_cli.group()
def jars():
    """Manage JAR files."""


@jars.command()
@click.argument("name")
@click.option("-V", "--mc-version", default="1.20.1")
@click.option("-r", "--build-version")
@click.option("-B", "--build-id")
def check(
    name: str,
    mc_version: str | None = None,
    build_version: str | None = None,
    build_id: str | None = None):
    """
    Construct a download URI and test it with a
    ping to the host.
    """

    mc  = minecraft_new(name, version_new(mc_version))
    jar = jars_jar_new(name ,build_version or mc_version, build_id)
    jars_jar_check(mc, jar)


@jars.command()
@click.argument("name")
@click.option("-V", "--mc-version", default="1.20.1")
@click.option("-r", "--build-version")
@click.option("-B", "--build-id")
def get(
    name: str,
    mc_version: str | None = None,
    build_version: str | None = None,
    build_id: str | None = None):
    """
    Download a single JAR file.
    """

    mc  = minecraft_new(name, version_new(mc_version))
    jar = jars_jar_new(name, build_version or mc_version, build_id)
    jars_download(mc, jar)


@jars.command()
@click.argument("name")
@click.option("-V", "--mc-version", default="1.20.1")
def getpkg(name: str, mc_version: str | None = None):
    """Download a package of JAR files."""

    mc  = minecraft_new(name, mc_version)
    jar = jars_jar_new(name)
    jars_download_package(mc, jar)


if __name__ == "__main__":
    exit(main_cli())
