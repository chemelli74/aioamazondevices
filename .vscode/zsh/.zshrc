# Workspace-scoped zsh startup used by VS Code terminals.
# Keep user-level shell customizations, then activate the project venv
# in this interactive shell so the prompt shows the virtualenv marker.

# Avoid local compdump files in the repository.
export ZSH_COMPDUMP="/tmp/.zcompdump-${USER:-vscode}"

if [ -f "$HOME/.zshrc" ]; then
  source "$HOME/.zshrc"
fi

if [ -f "$PWD/.venv/bin/activate" ]; then
  source "$PWD/.venv/bin/activate"
fi
