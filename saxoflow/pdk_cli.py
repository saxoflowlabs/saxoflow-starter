"""CLI commands for SaxoFlow's manifest-driven PDK registry."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import click
import yaml

from saxoflow.pdk_registry import (
    RegistryError,
    activate_external_platform,
    activate_orfs_platform,
    all_manifests,
    get_manifest,
    installation_metadata_path,
    is_installed,
    load_manifest,
    manifest_template,
    data_home,
    platform_root,
    read_installation,
    record_installation_checksums,
    registry_dir,
    remove_installation,
    run_platform_smoke_test,
    validate_openroad_technology,
    verify_installation,
    verify_platform_root,
)


def _fail(exc: Exception) -> None:
    raise click.ClickException(str(exc)) from exc


@click.group("pdk")
def pdk() -> None:
    """Manage versioned PDK and OpenROAD platform integrations."""


@pdk.command("list")
def list_pdks() -> None:
    """List available platforms and installation state."""
    manifests = all_manifests()
    if not manifests:
        click.echo("No PDK platform manifests are registered.")
        return

    headers = (
        "PLATFORM",
        "FAMILY",
        "SUPPORT",
        "STATE",
        "VERSION",
        "ORFS",
        "OPENROAD",
        "LIBRARIES",
        "CORNERS",
    )

    def row_for(manifest):
        libraries = ",".join(str(item.get("id")) for item in manifest.libraries)
        corners = ",".join(
            sorted(
                {
                    str(corner.get("id"))
                    for library in manifest.libraries
                    for corner in library.get("corners", [])
                }
            )
        )
        revision = str(
            (read_installation(manifest) or {}).get(
                "source_revision",
                manifest.version,
            )
        )[:12]
        return (
            manifest.id,
            manifest.family,
            manifest.classification,
            "installed" if is_installed(manifest) else "available",
            revision,
            str(manifest.compatibility.get("orfs_revision", "unspecified"))[:12],
            str(
                manifest.compatibility.get(
                    "openroad_revision",
                    manifest.compatibility.get("openroad", "unspecified"),
                )
            )[:12],
            libraries,
            corners,
        )

    groups = (
        (
            "Fabrication-oriented platforms",
            [
                manifest
                for manifest in manifests
                if manifest.classification in {"validated", "experimental"}
            ],
        ),
        (
            "Research reference platforms",
            [
                manifest
                for manifest in manifests
                if manifest.classification == "reference"
            ],
        ),
        (
            "Custom platforms",
            [
                manifest
                for manifest in manifests
                if manifest.classification == "custom"
            ],
        ),
    )
    rows = [row_for(manifest) for manifest in manifests]
    widths = [
        max(len(headers[index]), *(len(str(row[index])) for row in rows))
        for index in range(len(headers))
    ]
    for title, group in groups:
        if not group:
            continue
        click.secho(title, fg="cyan", bold=True)
        click.echo(
            "  ".join(
                headers[index].ljust(widths[index])
                for index in range(len(headers))
            )
        )
        for manifest in group:
            row = row_for(manifest)
            click.echo(
                "  ".join(
                    str(row[index]).ljust(widths[index])
                    for index in range(len(headers))
                )
            )
        click.echo()


@pdk.command("info")
@click.argument("identifier")
def pdk_info(identifier: str) -> None:
    """Show platform metadata, libraries, corners, and installation details."""
    try:
        manifest = get_manifest(identifier)
    except RegistryError as exc:
        _fail(exc)
        return

    click.echo(f"Platform: {manifest.id}")
    click.echo(f"Family: {manifest.family}")
    click.echo(f"Provider: {manifest.provider}")
    click.echo(f"Classification: {manifest.classification}")
    click.echo(f"Support: {manifest.support_status}")
    click.echo(f"Version: {manifest.version}")
    click.echo(f"ORFS revision: {manifest.compatibility.get('orfs_revision', 'unspecified')}")
    click.echo(
        "OpenROAD revision: "
        f"{manifest.compatibility.get('openroad_revision', 'unspecified')}"
    )
    click.echo(f"Synthesis handoff: {manifest.synthesis.get('mode')}")
    if manifest.install.get("estimated_download_mb"):
        click.echo(
            "Estimated download: "
            f"{manifest.install['estimated_download_mb']} MiB"
        )
    if manifest.install.get("required_disk_mb"):
        click.echo(
            "Required free disk: "
            f"{manifest.install['required_disk_mb']} MiB"
        )
    click.echo(f"Description: {manifest.description}")
    click.echo(f"Installed: {'yes' if is_installed(manifest) else 'no'}")
    root = platform_root(manifest)
    if root:
        click.echo(f"Platform root: {root}")
    aliases = ", ".join(manifest.aliases) or "none"
    click.echo(f"Aliases: {aliases}")
    physical = manifest.physical
    click.echo(f"Placement site: {physical.get('site', 'unspecified')}")
    click.echo(
        "Routing layers: "
        f"{physical.get('min_routing_layer', 'unspecified')} to "
        f"{physical.get('max_routing_layer', 'unspecified')}"
    )
    environment = ", ".join(manifest.required_environment) or "none"
    click.echo(f"Required environment: {environment}")
    tooling = ", ".join(
        f"{tool} ({len(artifacts)} artifact(s))"
        for tool, artifacts in manifest.tooling.items()
    ) or "none"
    click.echo(f"Tool configuration: {tooling}")
    license_data = manifest.license
    click.echo(f"License: {license_data.get('name', 'unspecified')}")
    if license_data.get("url"):
        click.echo(f"License URL: {license_data['url']}")
    click.echo("Libraries:")
    for library in manifest.libraries:
        corners = ", ".join(
            str(corner.get("id")) for corner in library.get("corners", [])
        )
        site = library.get("physical", {}).get(
            "site",
            manifest.physical.get("site"),
        )
        site_text = f"; site={site}" if site else ""
        click.echo(f"  {library.get('id')}: {corners}{site_text}")


@pdk.command("install")
@click.argument("identifier")
@click.option(
    "--root",
    type=click.Path(file_okay=False, path_type=Path),
    help="Existing platform root for an external manifest.",
)
@click.option(
    "--accept-license",
    is_flag=True,
    help="Confirm acceptance of the platform's upstream license.",
)
def pdk_install(
    identifier: str,
    root: Optional[Path],
    accept_license: bool,
) -> None:
    """Activate one PDK platform without copying user-managed PDK content."""
    try:
        manifest = get_manifest(identifier)
        if is_installed(manifest):
            click.echo(
                f"Platform `{manifest.id}` is already installed at "
                f"{platform_root(manifest)}."
            )
            return

        license_name = manifest.license.get("name", "the upstream license")
        click.echo(f"License: {license_name}")
        if manifest.license.get("url"):
            click.echo(f"License URL: {manifest.license['url']}")
        estimated_download = manifest.install.get("estimated_download_mb")
        required_disk = manifest.install.get("required_disk_mb")
        if estimated_download:
            click.echo(
                f"Estimated download for pinned collateral: {estimated_download} MiB"
            )
        if required_disk:
            click.echo(f"Required free disk space: {required_disk} MiB")
        if not accept_license:
            raise RegistryError(
                f"Review {license_name} for `{manifest.id}`, then rerun with "
                "`--accept-license`."
            )
        if required_disk:
            storage_root = data_home()
            storage_root.mkdir(parents=True, exist_ok=True)
            free_mb = shutil.disk_usage(storage_root).free // (1024 * 1024)
            if free_mb < int(required_disk):
                raise RegistryError(
                    f"`{manifest.id}` requires {required_disk} MiB free under "
                    f"{storage_root}, but only {free_mb} MiB is available."
                )

        kind = manifest.install.get("kind")
        if kind == "orfs-platform":
            if root is not None:
                raise RegistryError(
                    "--root is only valid for manifests with install kind `external`."
                )
            click.echo(
                "Materializing only the selected platform collateral from the "
                "pinned ORFS revision."
            )
            installed_root = activate_orfs_platform(manifest)
        else:
            if root is None:
                raise RegistryError(
                    f"`{manifest.id}` uses external PDK collateral. Pass --root DIR."
                )
            installed_root = activate_external_platform(manifest, root)

        problems = verify_installation(manifest)
        if problems:
            remove_installation(manifest)
            raise RegistryError(
                "Platform activation failed verification:\n  "
                + "\n  ".join(problems)
            )
        checksums = record_installation_checksums(manifest)
    except RegistryError as exc:
        _fail(exc)
        return

    click.secho(
        f"SUCCESS: Activated `{manifest.id}` from {installed_root}.",
        fg="green",
    )
    click.echo(f"Recorded {len(checksums)} platform artifact checksum group(s).")
    if manifest.classification in {"experimental", "reference"}:
        click.secho(
            f"WARNING: `{manifest.id}` is classified as "
            f"{manifest.classification}: {manifest.support_status}.",
            fg="yellow",
        )


@pdk.command("verify")
@click.argument("identifier")
def pdk_verify(identifier: str) -> None:
    """Verify the active platform root and required artifacts."""
    try:
        manifest = get_manifest(identifier)
        problems = verify_installation(manifest)
    except RegistryError as exc:
        _fail(exc)
        return
    if problems:
        for problem in problems:
            click.secho(f"ERROR: {problem}", fg="red")
        raise click.ClickException(f"Platform `{manifest.id}` failed verification.")
    click.secho(
        f"SUCCESS: `{manifest.id}` platform artifacts are available.",
        fg="green",
    )


@pdk.command("remove")
@click.argument("identifier")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation.")
def pdk_remove(identifier: str, yes: bool) -> None:
    """Remove managed collateral or external-platform activation metadata."""
    try:
        manifest = get_manifest(identifier)
    except RegistryError as exc:
        _fail(exc)
        return
    metadata = read_installation(manifest)
    if metadata is None:
        click.echo(f"Platform `{manifest.id}` is not activated.")
        return
    if not yes and not click.confirm(
        f"Remove SaxoFlow activation metadata for `{manifest.id}`?"
    ):
        click.echo("Cancelled.")
        return
    try:
        remove_installation(manifest)
    except RegistryError as exc:
        _fail(exc)
        return
    click.secho(
        f"SUCCESS: Removed SaxoFlow-managed state for `{manifest.id}`.",
        fg="green",
    )


@pdk.command("register")
@click.option(
    "--manifest",
    "manifest_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--replace", is_flag=True, help="Replace an existing custom manifest.")
@click.option(
    "--root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Validate and activate this existing external platform root.",
)
@click.option(
    "--smoke-test",
    is_flag=True,
    help="Run the manifest-provided synthesis/floorplan smoke-test adapter.",
)
def pdk_register(
    manifest_path: Path,
    replace: bool,
    root: Optional[Path],
    smoke_test: bool,
) -> None:
    """Register a validated custom platform manifest."""
    try:
        manifest = load_manifest(manifest_path)
        if manifest.classification != "custom":
            raise RegistryError(
                "User-registered manifests must use classification `custom`."
            )
        target_dir = registry_dir()
        target = target_dir / f"{manifest.id}.yaml"
        if target.exists() and not replace:
            raise RegistryError(
                f"A custom manifest for `{manifest.id}` already exists. Use --replace."
            )
        if root is not None:
            resolved_root = root.expanduser().resolve()
            problems = verify_platform_root(manifest, resolved_root)
            if problems:
                raise RegistryError(
                    "Custom platform verification failed:\n  "
                    + "\n  ".join(problems)
                )
            openroad = shutil.which("openroad")
            if not openroad:
                raise RegistryError(
                    "OpenROAD is required for the read-only technology-load test."
                )
            validate_openroad_technology(manifest, resolved_root, openroad)
            if smoke_test:
                output = run_platform_smoke_test(manifest, resolved_root)
                if output:
                    click.echo(output)
        elif smoke_test:
            raise RegistryError("--smoke-test requires --root.")
        target_dir.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        shutil.copyfile(manifest_path, temporary)
        temporary.replace(target)
        if root is not None:
            activate_external_platform(manifest, root)
    except (OSError, RegistryError) as exc:
        _fail(exc)
        return
    click.secho(f"SUCCESS: Registered `{manifest.id}` at {target}.", fg="green")
    if root is None:
        click.echo(
            f"Next: saxoflow pdk install {manifest.id} --root /path/to/platform "
            "--accept-license"
        )
    else:
        click.echo("Read-only OpenROAD technology-load test passed.")
        if smoke_test:
            click.echo("Platform synthesis/floorplan smoke test passed.")


@pdk.command("template")
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
)
@click.option("--force", is_flag=True, help="Overwrite an existing file.")
def pdk_template(output: Path, force: bool) -> None:
    """Write a custom platform manifest template."""
    path = output.expanduser().resolve()
    if path.exists() and not force:
        raise click.ClickException(f"Output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(manifest_template(), sort_keys=False),
        encoding="utf-8",
    )
    click.secho(f"SUCCESS: Wrote platform manifest template to {path}.", fg="green")


__all__ = [
    "pdk",
    "list_pdks",
    "pdk_info",
    "pdk_install",
    "pdk_verify",
    "pdk_remove",
    "pdk_register",
    "pdk_template",
]
