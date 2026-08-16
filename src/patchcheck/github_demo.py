import changeguard.github_demo as _legacy
from changeguard.github_demo import *  # compatibility re-export


def _patchcheck_markdown(result, max_findings=12):
    return _legacy.render_markdown(result, max_findings=max_findings).replace("## ChangeGuard review", "## PatchCheck review")


def _cli():
    _legacy.render_markdown = _patchcheck_markdown
    _legacy._cli()


if __name__ == "__main__":
    _cli()
