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
import getpass
import os
import pathlib
import re
import subprocess
import textwrap
import tomllib
import typing
import zipfile
from urllib.error import HTTPError

import click, httpx, jproperties, mctools, wget

# -----------------------------------------------
# Common script objects.
# -----------------------------------------------

T = typing.TypeVar("T")
JarConfResponse = typing.Mapping[str, T]
Service = None
ServiceT = str | int | Service
Unset = type("Unset", (int,), {})
Version  = None
VersionT = str | tuple[str | int, ...] | Version

REGEX_CAMEL_CASE        = re.compile(r"([A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$)))|_")
REGEX_FMT_ARG_SPECIFIER = lambda arg: (re.compile(r"\{%s\}" % (arg,)))
REGEX_FMT_KWD_SPECIFIER = lambda kwd: (re.compile(r"\{%s:[\w\-_]+\}" % (kwd,)))


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


class JarPackage(typing.NamedTuple):
    """
    Collection Jar files and additional metadata.
    """

    name:          str
    from_packages: str | typing.Self | typing.Sequence[typing.Self] | None
    depends:       typing.Sequence[JarFile] | None
    service:       "Service"
    service_port:  int
    service_host:  str
    rcon_port:     int
    rcon_password: str


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

ServiceServer = (Service.Paper, Service.Velocity)


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


def make_jarname(mc: Minecraft, svc: Service) -> pathlib.Path:
    """
    Returns a concatentated version of the passed
    values as jar path.
    """

    root  = (mc.jar_root / str(mc.version))
    name  = str(svc)
    parts = ["*", "*"]

    if svc is Service.Paper:
        parts[0] = str(mc.jar_svr_ver)
        if int(mc.jar_svr_bld) >= 0:
            parts[1] = str(mc.jar_svr_bld)

    elif svc is Service.Velocity:
        if mc.jar_pxy_ver.major >= 0:
            parts[0] = str(mc.jar_pxy_ver)
        if mc.jar_pxy_bld >= 0:
            parts[1] = str(mc.jar_pxy_bld)

    name = "-".join((name, *parts)) + ".jar"
    if "*" in name:
        # Find the first available build.
        return next(root.rglob(name))

    return (root / name)


def svc_arch_include(mc: Minecraft, svc: Service) -> tuple[pathlib.Path, ...]:
    """Gets the include file list."""

    exe_from = (mc.exe_root / mc.exe_name)
    include  = ()

    # Define what files we want to preserve
    # in our backup.
    if svc is Service.Paper or Service.Paper in svc:
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


def svc_new(
    svc: ServiceT | None = None, 
    default: ServiceT | None = None) -> Service:
    """Return a services instance."""

    def isservice(s):
        return isinstance(s, Service)

    def isseviceiter(s):
        return isinstance(s, typing.Iterable) and all(map(isservice, s)) 

    if not svc:
        return default or Service.Paper
    if isinstance(svc, Service):
        return svc
    if isseviceiter(svc):
        return svc
    if isinstance(svc, int):
        return Service(svc) #type: ignore
    if isinstance(svc, str):
        return Service[snake2camel(svc)]

    raise TypeError(f"Unsupported conversion from {svc!r} to {Service}")


def svc_opts_apply(
    fn: typing.Callable,
    opts: typing.Sequence[typing.Callable]) -> typing.Callable:
    """Wrap function with CLI options."""

    for o in opts:
        fn = o(fn)
    return fn


def svc_opts_common(fn: typing.Callable) -> typing.Callable:
    """Wrap function with common CLI options."""

    opts = (
        click.argument("name"),
        click.option("-s", "--service", "svc"),
        click.option("-V", "--mc-version", default="1.20.1"))
    return svc_opts_apply(fn, opts)


def svc_opts_java(fn: typing.Callable) -> typing.Callable:
    """Wrap function with common Java options."""

    opts = (
        click.option("-m", "--mem-ini"),
        click.option("-M", "--mem-max"))
    return svc_opts_apply(fn, opts)


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


def jars_cfg_ispkg(cfg: typing.Mapping, name: str):
    """
    Whether or not a configuration is package
    configuration.
    """

    fields = (
        "depends",
        "from"
    )

    parent = name.rsplit(".", maxsplit=1)[0]
    return any(map(lambda k: k in fields, cfg)) and parent == "jars.packages"


def jars_cfg_load(mc: Minecraft) -> typing.Mapping:
    """Loads the jars configuration."""

    return tomllib.loads(jars_cfg(mc).read_text())


def jars_cfg_fmt(
    mc: Minecraft,
    jar: JarFile,
    jcr: JarConfResponse) -> JarConfResponse:
    """
    Format keyword values found in a
    `JarConfResponse`.
    """

    def getvar(kwd):
        reg = REGEX_FMT_KWD_SPECIFIER(kwd)
        return reg.findall(itm)[0].strip("}{").split(":", 2)[1]

    def isunset(arg):
        reg = REGEX_FMT_ARG_SPECIFIER(arg)
        return arg not in params and len(reg.findall(itm))

    def isunsetvar(kwd):
        reg = REGEX_FMT_KWD_SPECIFIER(kwd)
        return kwd not in params and len(reg.findall(itm))

    def mapget(m):
        return m.get(jar.name, tuple(m.values())[0])

    def panic(kwd):
        click.echo(
            f"{jar.name}: {kwd!r} is required to build property.",
            err=True)
        quit(1)

    def replvar(kwd):
        reg = REGEX_FMT_KWD_SPECIFIER(kwd)
        return reg.subn("{" + kwd + "}", itm, 1)[0]

    params = dict()
    itm    = mapget(jcr)
    while re.findall(r"\{.*\}", itm):
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
            itm = replvar("host")

        if isunset("name"):
            spec_name = jars_jar_name(mc, jar, {})
            if not spec_name:
                panic("name")
            params["name"] = spec_name[jar.name]

        if isunset("version"):
            if not (jar.version or mc.version):
                panic("version")
            params["version"] = version_new(jar.version or mc.version)

        itm = itm.format_map(params)

    return itm


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
        parent = ".".join(parts[:idx])

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
            # If reverse lookup fails
            elif jars_cfg_ispkg(config, parent):
                return config

        # If the current path part can't be found
        # in the current map, bail on the loop.
        if part not in config:
            config = Unset
            break
        config = config[part]

    # If no default is provided, and the lookup
    # failed, panic.
    if config is Unset and default is Unset:
        raise KeyError(f"{part!r} does not exist in {parent!r}")

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

        tmp = jars_jar_new(name, jar.version, jar.build, jar.service)
        if jars_download_exists(mc, jar, url):
            click.echo(
                f"{tmp} already installed for version {mc.version}",
                err=True)
            continue

        try:
            res = wget.download(url, str(dst))
            # Progress bar for wget.download does not
            # print a new line on its own.
            click.echo("\n")
        except HTTPError as err:
            if jars_jar_check(mc, jar):
                res = httpx.get(url)
            else:
                click.echo(
                    f"failed to download {jar} <{err.status} {err.reason}>",
                    err=True)
                return

        # Check that url name and JAR name match
        # if JAR name exists in jars config.
        url_name = wget.detect_filename(url)
        jar_name = jars_jar_name(mc, jar, {}).get(name, "notfound")

        if isinstance(res, httpx.Response):
            (dst / url_name).write_bytes(res.content)
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


def jars_download_package(mc: Minecraft):
    """Downloads JAR files from target package."""

    pkgs = jars_jar_package(mc)
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
        click.echo(f"{name}: {url} <{r.status_code} {r.reason_phrase}>")

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

    names = jars_cfg_opt(mc, f"jars.uri.special.names.{jar.name}", default)
    if names is default:
        return default

    for name in names:
        names[name] = jars_cfg_fmt(mc, jar, {name: names[name]})
    return names


def jars_jar_new(
    name: str,
    version: VersionT | None = None,
    build:  str | int | None = None,
    service: Service | str | None = None) -> JarFile:
    """Constructs new `JarFile`. representation."""

    build   = str(build) if build else ""
    version = version_new(version)
    svc = svc_new(service, Service.Plugin)

    return JarFile(build, name, version, svc)


def jars_jar_package(mc: Minecraft, jar: JarFile | None = None) -> JarConfResponse[JarPackage]:
    """
    Get the package, or packages associated with
    this `JarFile`
    """

    def hasinvalidkeys(m):
        return any(map(lambda k: not ispackagekey(k), m))

    def ispackagekey(k):
        return k in pkg_keys

    pkg_keys = (
        "depends",
        "from",
        "service",
        "service_port",
        "service_host",
        "rcon_port",
        "rcon_password")
    pkg_txlpairs = (
        ("from_packages", "from"),
        ("svc", "service"),
        ("svc_host", "service_host"),
        ("svc_port", "service_port")
    )

    jar  = jar or jars_jar_new(mc.pkg_name or mc.exe_name)
    path = ("jars", "packages", jar.name)
    if jar.version:
        path += (str(jar.version).replace(".", "_"),)
    pkgs = jars_cfg_opt(mc, ".".join(path))

    for name, pkg in tuple(pkgs.items()):
        if hasinvalidkeys(pkg):
            pkgs.pop(name)
            continue

        # Translate manifest keywords to
        # constructor keywords.
        for new, old in pkg_txlpairs:
            pkg[new] = pkg.pop(old, None)

        pkgs[name] = jars_package_new(mc, name, **pkg)

    return pkgs


def jars_jar_url(mc: Minecraft, jar: JarFile) -> JarConfResponse[str]:
    """
    Constructs a JAR download URL from
    configuration.
    """

    jars = [jar]
    if "*" in jar.name:
        jars = jars_jar_name(mc, jar)
        jars = [jars_jar_new(n, jar.version, jar.build) for n in jars]
        return {j.name:jars_jar_url(mc, j)[j.name] for j in jars}

    # There's a possibility of the reverse lookup
    # to produce multiple, one or no definitions.
    definitions = jars_jar_definition(mc, jar)
    params      = dict()
    return {jar.name: jars_cfg_fmt(mc, jar, definitions)}


def jars_link(mc: Minecraft, jar: JarFile) -> None:
    """
    Links a jar file to a `Minecraft service.
    """

    if jar.service is not Service.Plugin:
        click.echo(f"{jar} does not require linking.", err=True)
        return

    src   = (mc.jar_root / str(mc.version))
    dst   = (mc.exe_root / mc.exe_name / "plugins")
    names = jars_jar_name(mc, jar, jars_jar_url(mc, jar))

    for _, name in names.items():
        name = wget.detect_filename(name)
        tmp  = jars_jar_new(name, jar.version, jar.build)

        if not jars_download_exists(mc, tmp, name):
            click.echo(f"{tmp} could not be found in JARs cache.", err=True)
            continue
        if (dst / name).exists():
            click.echo(f"{tmp} already linked to {mc.exe_name!r}.", err=True)
            continue

        os.link((src / name), (dst / name))


def jars_link_package(mc: Minecraft):
    """
    Links a JAR package to a `Minecraft`
    service.
    """

    for name, pkg in jars_jar_package(mc).items():
        click.echo(f"creating links for package {name!r}")
        for j in pkg.depends:
            jars_link(mc, j)


def jars_package_new(
    mc: Minecraft,
    name: str,
    from_packages: str | JarPackage | typing.Sequence[str | JarPackage] | None = None,
    depends: typing.Sequence[JarFile] | None = None,
    svc: ServiceT | None = None,
    svc_port: int | None = None,
    svc_host: str | None = None,
    rcon_port: int | None = None,
    rcon_password: str | None = None) -> JarPackage:
    """Create a new `JarPackage` instance."""

    def from_pkgs(pkgs, cls=None):
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
                    pkg.get("depends", None),
                    pkg.get("service", None),
                    pkg.get("service_port", None),
                    pkg.get("service_host", None),
                    pkg.get("rcon_port", None),
                    pkg.get("rcon_password", None))
            elif cls is JarFile:
                pkg = jars_jar_new(**pkg)

            pkgs[idx] = pkg

        return tuple(pkgs)

    def panic(kwd):
        click.echo(
            f"{name} {kwd!r} is required to build package.", err=True)
        quit(1)

    if depends:
        depends = from_pkgs(depends, JarFile)

    if isinstance(from_packages, (str, JarPackage)):
        from_packages = [from_packages]
    if from_packages:
        from_packages = from_pkgs(from_packages, JarPackage)
    
    from_packages = (from_packages or ())
    depends       = set(depends or ())

    for pkg in from_packages:

        for d in (pkg.depends or ()):
            depends.add(d)

        svc           = svc or pkg.service
        svc_port      = svc_port or pkg.service_port
        svc_host      = svc_host or pkg.service_host
        rcon_port     = rcon_port or pkg.rcon_port
        rcon_password = rcon_password or pkg.rcon_password

    depends       = tuple(depends)
    from_packages = from_packages or None
    return JarPackage(
        name,
        from_packages,
        depends,
        svc,
        svc_port,
        svc_host,
        rcon_port,
        rcon_password)


# -----------------------------------------------
# Minecraft specific utilities. Used for
# executing and organizing services.
# -----------------------------------------------

def minecraft_archive(
    mc: Minecraft,
    svc: Service | None,
    preserve: bool | None = None):
    """Archive the target service(s)."""

    # Find pacakge information related to each
    # service.

    # Find all service directories that match the
    # given service.

    def isvalidpkg(pkg):
        return (
            pkg.service in svc
            if isinstance(svc, typing.Iterable)
            else pkg.servcie is svc)

    if "*" in mc.exe_name:
        pkgs = jars_jar_package(mc)
    elif mc.exe_name == "all":
        pkgs = jars_jar_package(mc, jars_jar_new("*"))
    else:
        minecraft_archive_one(mc, svc, preserve)
        return

    for name, pkg in pkgs.items():
        if not isvalidpkg(pkg):
            continue
        tmp = minecraft_new(name, mc.version, pkg.name)
        minecraft_archive_one(tmp, pkg.service, preserve)


def minecraft_archive_one(
        mc: Minecraft,
        svc: Service,
        preserve: bool | None = None):
    """Archive the target service."""

    exe_from = (mc.exe_root / mc.exe_name)
    if not exe_from.exists():
        return

    include = svc_arch_include(mc, svc)
    if not include:
        return

    with archive_write(mc, preserve) as bak:

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


def minecraft_svc_start(
    mc: Minecraft,
    svc: Service,
    xms: str | None = None,
    xmx: str | None = None):
    """
    Starts a single Minecraft server.

    ---
    `xms`: Initial heap size.

    `xmx`: Maximum heap size.
    """

    if svc is Service.Velocity:
        minecraft_server_pxy_start(mc, xms, xmx)
    if svc is Service.Paper:
        minecraft_server_svr_start(mc, xms, xmx)

# -----------------------------------------------
# Miner Command Line Interface.
# -----------------------------------------------

@click.group()
def main_cli():
    """Manage Aabernathy services."""


@main_cli.command()
@svc_opts_common
@svc_opts_java
def start(
    name: str,
    svc: Service | None = None,
    mc_version: str | None = None,
    mem_ini: str | None = None,
    mem_max: str | None = None):
    """Start a service."""

    svc = svc_new(svc)
    mc = minecraft_new(name, version_new(mc_version))

    minecraft_server_init(mc)
    minecraft_svc_start(mc, svc, mem_ini, mem_max)


@main_cli.command()
@click.argument("name", nargs=-1)
@click.option("-s", "--service", "svc")
@click.option("-V", "--mc-version", default="1.20.1")
@click.option("--preserve", is_flag=True)
def backup(
    name: tuple[str],
    svc: Service | None = None,
    mc_version: str | None = None,
    preserve: bool | None = None):
    """Create a backup of a service."""

    svc = svc_new(svc, default=ServiceServer)
    for n in name:
        mc  = minecraft_new(n, version_new(mc_version))
        minecraft_archive(mc, svc, preserve)


@main_cli.command()
@svc_opts_common
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

    mc = minecraft_new(name, mc_version)
    jars_download_package(mc)


@jars.command()
@click.argument("name")
@click.option("-V", "--mc-version", default="1.20.1")
def chkpkg(name: str, mc_version: str | None = None):
    """Retrieve package information."""

    mc = minecraft_new(name, mc_version)
    pkgs = jars_jar_package(mc)
    for pkg in pkgs.values():
        click.echo(f"Package: {pkg.name} ServiceType: {pkg.service}")
        if pkg.depends:
            click.echo(f"Depends On({len(pkg.depends)}):")
            for d in pkg.depends:
                click.echo(f"    - {d.name}:{d.version}")
        if pkg.from_packages:
            click.echo(f"From Packages({len(pkg.from_packages)}):")
            for p in pkg.from_packages:
                click.echo(f"    - {p.name}")
        if any([pkg.service_host, pkg.service_port, pkg.rcon_port]):
            click.echo(textwrap.dedent(f"""\
            Network Info:
                Host:      {pkg.service_host if pkg.service_host else 'unset'}
                Port:      {pkg.service_port if pkg.service_port else 'unset'}
                RCON Port: {pkg.rcon_port if pkg.rcon_port else 'unset'}
                RCON Pass: {'*'*10 if pkg.rcon_password else 'unset'}
            """))


@jars.command()
@click.argument("name")
@click.argument("dst")
@click.option("-V", "--mc-version", default="1.20.1")
@click.option("--download", is_flag=True)
def lnkpkg(name: str, dst: str, *, mc_version: str, download: bool):
    """
    Link package files to target service assets.
    """

    mc = minecraft_new(dst, mc_version, pkg_name=name)

    if download:
        jars_download_package(mc)

    jars_link_package(mc)


@main_cli.command()
@click.argument("cmd", nargs=-1)
@click.option("-p", "--port", default=os.getenv("MINER_RCON_PORT", 25575))
@click.option("-H", "--host", default=os.getenv("MINER_RCON_HOST", "locahost"))
@click.option("--password", default=os.getenv("MINER_RCON_PASSWORD", None))
@click.option("-P", "--package", "pkg")
@click.option("-V", "--package-version", "pkg_version", default="1.20.1")
def shell(
    cmd: str,
    *,
    port: int,
    host: str,
    password: str,
    pkg: str | JarPackage,
    pkg_version: str):
    """Connect to a remote console."""

    name = host
    if pkg:
        pkg = jars_jar_package(minecraft_new(pkg, pkg_version))[pkg]
        if pkg.service not in (Service.Paper,):
            click.echo(
                "target service does not support RCON protocol.",
                err=True)
            quit(1)

        port     = pkg.rcon_port or port
        host     = pkg.service_host or host
        password = pkg.rcon_password or password
        if pkg.name:
            name = f"{pkg.name}({host}{':' + str(port) if port else ''})"
        rep_name = pkg.name or host

    def handleauth():
        try:
            rt = rcon.login(password or getpass.getpass("password: "))
        except Exception as error:
            click.echo(error, err=True)
            quit(1)

        if not rt:
            click.echo("authentication failed", err=True)
            quit(1)

    def handlecmd(cmd):
        if cmd in ("q", "Q"):
            quit(0)

        rt = rcon.command(cmd)
        if not rt:
            click.echo("bad response from remote.", err=True)
            quit(1)
        click.echo(rt.encode())

    with mctools.RCONClient(host, port) as rcon:
        handleauth()
        click.echo(f"MinerShell@{name} Connected.")
        if cmd:
            handlecmd(cmd)
            return

        while True:
            try:
                handlecmd((cmd := input(f"{rep_name}$ ")))
            except KeyboardInterrupt:
                click.echo()


if __name__ == "__main__":
    exit(main_cli())
