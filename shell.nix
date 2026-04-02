{ pkgs ? import <nixpkgs> { } }:

let
  pythonEnv = pkgs.python312.withPackages (ps: with ps; [
    ps.pip
    ps.numpy
    ps.uv

    # Include any additional Python packages here
  ]);
in
pkgs.mkShell {
  buildInputs = [
    pythonEnv
    pkgs.commitlint-rs
    pkgs.nodejs  # Add Node.js here

  ];

  shellHook = ''
    uv sync --group dev
    source .venv/bin/activate
    scripts/setup.sh
  '';
}
