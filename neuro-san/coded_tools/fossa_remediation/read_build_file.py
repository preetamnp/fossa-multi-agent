"""Read files from the cloned repo workspace for agent reasoning."""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from workspace import (
    default_build_filename,
    require_workspace,
    resolve_relative_path,
    store_tool_result,
)


class ReadRepoFile(CodedTool):
    """Return a repo-relative file excerpt; paths are resolved under the workspace root."""

    DEFAULT_MAX_CHARS = 6000

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        ws, error = require_workspace(sly_data, repo_name)
        if error:
            return error
        assert ws is not None

        relative_path = args.get("relative_path") or args.get("filename")
        if not relative_path:
            relative_path = default_build_filename(ws.build_tool)

        path, path_error = resolve_relative_path(ws.root, str(relative_path))
        if path_error:
            return path_error
        assert path is not None

        if not path.exists():
            return f"{relative_path} not found in workspace for {repo_name}."

        content = path.read_text(encoding="utf-8")
        max_chars = int(args.get("max_chars") or self.DEFAULT_MAX_CHARS)
        excerpt = content[:max_chars]
        if len(content) > max_chars:
            excerpt += f"\n... truncated ({len(content) - max_chars} more chars)"

        lang = "xml" if path.suffix in {".xml", ".gradle"} else path.suffix.lstrip(".") or "text"
        result = {
            "tool": "ReadRepoFile",
            "repo_name": repo_name,
            "ok": True,
            "phase": "read_file",
            "relative_path": str(relative_path),
            "size_bytes": len(content.encode("utf-8")),
            "truncated": len(content) > max_chars,
        }
        store_tool_result(sly_data, repo_name, "ReadRepoFile", result)

        return (
            f"Contents of `{relative_path}` in {repo_name}:\n"
            f"```{lang}\n{excerpt}\n```"
        )


class ReadBuildFile(ReadRepoFile):
    """Backward-compatible alias: reads pom.xml or build.gradle by default."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        if not args.get("filename") and not args.get("relative_path"):
            ws, error = require_workspace(sly_data, args.get("repo_name"))
            if error:
                return error
            assert ws is not None
            args = dict(args)
            args["relative_path"] = default_build_filename(ws.build_tool)
        return await super().async_invoke(args, sly_data)
