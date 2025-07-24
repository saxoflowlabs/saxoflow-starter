import os
import click

def write_output(output, output_file=None, default_folder=None, default_name=None, ext=".v"):
    if output_file:
        out_path = output_file
    else:
        os.makedirs(default_folder, exist_ok=True)
        out_path = os.path.join(default_folder, default_name + ext)
    with open(out_path, 'w') as f:
        f.write(output)
    click.secho(f"[✔] Output written to: {out_path}", fg="green")
    return out_path

def base_name_from_path(path):
    return os.path.splitext(os.path.basename(path))[0]
