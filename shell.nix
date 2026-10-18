{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  packages = with pkgs; [
    just
    python3
    ruff
    shellcheck
    melonds
    xdotool
    xvfb
    gdb
    imagemagick
  ];
}
