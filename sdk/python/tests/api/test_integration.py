import uuid
from datetime import datetime
from textwrap import dedent

import pytest

import dagger
from dagger.exceptions import ExecuteTimeoutError

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.slow,
]


async def test_container():
    async with dagger.Connection() as client:
        alpine = client.container().from_("alpine:3.16.2")
        version = await alpine.with_exec(["cat", "/etc/alpine-release"]).stdout()

        assert version == "3.16.2\n"


async def test_git_repository():
    async with dagger.Connection() as client:
        repo = client.git("https://github.com/dagger/dagger").tag("v0.3.0").tree()
        readme = await repo.file("README.md").contents()

        assert readme.split("\n")[0] == "## What is Dagger?"


async def test_container_build():
    async with dagger.Connection() as client:
        repo = client.git("https://github.com/dagger/dagger").tag("v0.3.0").tree()
        dagger_img = client.container().build(repo)

        out = await dagger_img.with_exec(["version"]).stdout()

        words = out.strip().split(" ")

        assert words[0] == "dagger"


async def test_container_with_env_variable():
    async with dagger.Connection() as client:
        container = (
            client.container().from_("alpine:3.16.2").with_env_variable("FOO", "bar")
        )
        out = await container.with_exec(["sh", "-c", "echo -n $FOO"]).stdout()

        assert out == "bar"


async def test_container_with_mounted_directory():
    async with dagger.Connection() as client:
        dir_ = (
            client.directory()
            .with_new_file("hello.txt", "Hello, world!")
            .with_new_file("goodbye.txt", "Goodbye, world!")
        )

        container = (
            client.container()
            .from_("alpine:3.16.2")
            .with_mounted_directory("/mnt", dir_)
        )

        out = await container.with_exec(["ls", "/mnt"]).stdout()

        assert out == dedent(
            """\
            goodbye.txt
            hello.txt
            """,
        )


async def test_container_with_mounted_cache():
    async with dagger.Connection() as client:
        cache_key = "example-cache"
        filename = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

        container = (
            client.container()
            .from_("alpine:3.16.2")
            .with_mounted_cache("/cache", client.cache_volume(cache_key))
        )

        for i in range(5):
            out = await container.with_exec(
                [
                    "sh",
                    "-c",
                    f"echo $0 >> /cache/{filename}.txt; cat /cache/{filename}.txt",
                    str(i),
                ],
            ).stdout()

        assert out == "0\n1\n2\n3\n4\n"


async def test_directory():
    async with dagger.Connection() as client:
        dir_ = (
            client.directory()
            .with_new_file("hello.txt", "Hello, world!")
            .with_new_file("goodbye.txt", "Goodbye, world!")
        )

        entries = await dir_.entries()

        assert entries == ["goodbye.txt", "hello.txt"]


async def test_host_directory():
    async with dagger.Connection() as client:
        readme = await client.host().directory(".").file("README.md").contents()
        assert "Dagger" in readme


async def test_execute_timeout():
    async with dagger.Connection(dagger.Config(execute_timeout=0.5)) as client:
        alpine = client.container().from_("alpine:3.16.2")
        with pytest.raises(ExecuteTimeoutError):
            await (
                alpine.with_env_variable("_NO_CACHE", str(uuid.uuid4()))
                .with_exec(["sleep", "2"])
                .stdout()
            )


async def test_query_error():
    async with dagger.Connection() as client:
        with pytest.raises(dagger.QueryError) as exc_info:
            await client.container().from_("ALPINE404").id()
    assert "repository name must be lowercase" in str(exc_info.value)


async def test_object_sequence(tmp_path):
    # Test that a sequence of objects doesn't fail.
    # In this case, we're using Container.export's
    # platform_variants which is a Sequence[Container].
    async with dagger.Connection() as client:
        variants = [
            client.container(platform=dagger.Platform(platform))
            .from_("alpine:3.16.2")
            .with_exec(["uname", "-m"])
            for platform in ("linux/amd64", "linux/arm64")
        ]
        await client.container().export(
            path=str(tmp_path / "export.tar.gz"),
            platform_variants=variants,
        )
