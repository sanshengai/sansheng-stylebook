#!/usr/bin/env python3
"""样图同步：样图只放在同仓的孤儿分支 `samples`，main 不跟踪 `styles/*/samples/**`。

  push    把工作区的样图提交到本地 samples 分支（不切分支、不碰 main 的索引与工作区；内容没变就不产生新提交）
  pull    把 origin/samples（没有就用本地 samples）里的样图解包回工作区
  status  对比工作区与 samples 分支头里的样图

锚点图（styles/<码>/anchor.*）与出图用的范例图不在 samples/ 下，属于 main，不受本脚本影响。
推送由维护者另行执行：git push origin samples
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "samples"
SAMPLE_GLOB = "styles/*/samples"


class SyncError(RuntimeError):
    pass


def _git(repo: Path, *args: str, env: dict | None = None, input: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    r = subprocess.run(["git", *args], cwd=repo, env=full_env, input=input, capture_output=True)
    if check and r.returncode != 0:
        raise SyncError(f"git {' '.join(args[:2])} 失败：{r.stderr.decode('utf-8', 'replace').strip()[-300:]}")
    return r


def _repo(path: Path) -> Path:
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path, capture_output=True, text=True)
    if r.returncode != 0:
        raise SyncError(f"{path} 不是 Git 仓库")
    return Path(r.stdout.strip())


def local_samples(repo: Path) -> list[str]:
    """工作区里 styles/<码>/samples/ 下的全部普通文件（仓库相对 POSIX 路径，排序）。"""
    out = []
    for d in sorted(repo.glob(SAMPLE_GLOB)):
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and not p.is_symlink() and not p.name.startswith("."):
                out.append(p.relative_to(repo).as_posix())
    return out


def _rev(repo: Path, ref: str) -> str | None:
    r = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    return r.stdout.decode().strip() if r.returncode == 0 else None


def pull_ref(repo: Path) -> str | None:
    """优先 origin/samples，其次本地 samples。"""
    for ref in (f"refs/remotes/origin/{BRANCH}", f"refs/heads/{BRANCH}"):
        if _rev(repo, ref):
            return ref
    return None


def tree_files(repo: Path, ref: str) -> dict[str, str]:
    """ref 树里的 路径 -> blob sha。"""
    raw = _git(repo, "ls-tree", "-rz", ref).stdout
    out = {}
    for rec in raw.split(b"\0"):
        if rec:
            head, path = rec.split(b"\t", 1)
            out[path.decode("utf-8")] = head.decode().split(" ")[2]
    return out


def push(repo: Path) -> str:
    files = local_samples(repo)
    if not files:
        raise SyncError("工作区没有样图（styles/*/samples/ 为空），拒绝提交空树；新克隆请先运行 pull")
    parent = _rev(repo, f"refs/heads/{BRANCH}")
    with tempfile.TemporaryDirectory() as td:
        env = {"GIT_INDEX_FILE": str(Path(td) / "index")}
        _git(repo, "add", "-f", "--pathspec-from-file=-", "--pathspec-file-nul", env=env,
             input=b"\0".join(f.encode("utf-8") for f in files))
        tree = _git(repo, "write-tree", env=env).stdout.decode().strip()
    if parent and _git(repo, "rev-parse", f"{parent}^{{tree}}").stdout.decode().strip() == tree:
        print(f"样图没有变化，samples 分支保持 {parent}（{len(files)} 个文件）", file=sys.stderr)
        return parent
    args = ["commit-tree", tree, "-m", f"样图快照：{len(files)} 个文件"]
    if parent:
        args += ["-p", parent]
    commit = _git(repo, *args).stdout.decode().strip()
    update = ["update-ref", f"refs/heads/{BRANCH}", commit]
    _git(repo, *update, *([parent] if parent else [""]))
    print(f"samples 分支已更新（{len(files)} 个文件）；推送请执行：git push origin {BRANCH}", file=sys.stderr)
    return commit


def pull(repo: Path, ref: str | None = None, overwrite: bool = True) -> int:
    ref = ref or pull_ref(repo)
    if not ref or not _rev(repo, ref):
        raise SyncError(f"找不到样图分支：请先 git fetch origin {BRANCH}:refs/remotes/origin/{BRANCH}，或确认本地已有 {BRANCH} 分支")
    names = list(tree_files(repo, ref))
    bad = [n for n in names if not (n.startswith("styles/") and "/samples/" in n and ".." not in n.split("/"))]
    if bad:
        raise SyncError(f"{ref} 里含 samples/ 以外的文件，拒绝解包：{bad[:3]}")
    archive = subprocess.Popen(["git", "archive", ref], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tar_cmd = ["tar", "-x", "-C", str(repo)] + ([] if overwrite else ["-k"])
    tar = subprocess.run(tar_cmd, stdin=archive.stdout, capture_output=True)
    archive.stdout.close()
    err = archive.stderr.read().decode("utf-8", "replace")
    if archive.wait() != 0 or tar.returncode != 0:
        raise SyncError(f"解包失败：{err.strip()[-200:] or tar.stderr.decode('utf-8', 'replace').strip()[-200:]}")
    print(f"已从 {ref} 解包 {len(names)} 个样图文件", file=sys.stderr)
    return len(names)


def status(repo: Path) -> dict:
    files = local_samples(repo)
    ref = f"refs/heads/{BRANCH}" if _rev(repo, f"refs/heads/{BRANCH}") else None
    branch = tree_files(repo, ref) if ref else {}
    hashes: dict[str, str] = {}
    if files:
        out = _git(repo, "hash-object", "--stdin-paths", input="\n".join(files).encode("utf-8")).stdout.decode().split()
        hashes = dict(zip(files, out))
    only_ws = sorted(set(hashes) - set(branch))
    only_br = sorted(set(branch) - set(hashes))
    differ = sorted(n for n in set(hashes) & set(branch) if hashes[n] != branch[n])
    res = {"local": len(hashes), "branch": len(branch), "only_local": len(only_ws),
           "only_branch": len(only_br), "different": len(differ), "head": _rev(repo, f"refs/heads/{BRANCH}")}
    print(f"工作区样图 {res["local"]}；samples 分支头 {res['branch']}（{res['head'] or '无分支'}）；"
          f"仅工作区 {res['only_local']}、仅分支 {res['only_branch']}、内容不同 {res['different']}")
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=ROOT, help="仓库目录（默认本脚本所在仓库）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("push", help="工作区样图 -> 本地 samples 分支")
    pl = sub.add_parser("pull", help="origin/samples（或本地 samples）-> 工作区")
    pl.add_argument("--ref", help="指定来源 ref；默认先 origin/samples 后本地 samples")
    pl.add_argument("--keep", action="store_true", help="已存在的同名文件不覆盖")
    sub.add_parser("status", help="对比工作区与 samples 分支头")
    a = ap.parse_args(argv)
    try:
        repo = _repo(a.repo)
        if a.cmd == "push":
            print(push(repo))
        elif a.cmd == "pull":
            pull(repo, a.ref, overwrite=not a.keep)
        else:
            status(repo)
    except SyncError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
