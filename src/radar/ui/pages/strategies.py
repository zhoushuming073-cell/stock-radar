"""Strategies page for the Streamlit UI.

Renders the installed strategy plugins, lets the user import a strategy ZIP,
and shows per-plugin details plus run history.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path

import streamlit as st


def render_strategies(manager) -> None:
    """Render the strategies page backed by the given plugin manager."""
    title, import_control = st.columns([5, 1], gap="small")
    with title:
        st.title("Strategies")
        st.caption("Manage your strategy plugins.")
    with import_control:
        with st.popover("＋ Import Strategy", width="stretch"):
            uploaded = st.file_uploader(
                "选择策略 ZIP", type=["zip"], key="strategies_import_uploader",
            )
            if uploaded is not None and st.button(
                "验证并导入", key="strategies_import_button"
            ):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir) / "strategy.zip"
                    tmp_path.write_bytes(uploaded.getvalue())
                    try:
                        manager.import_zip(tmp_path)
                        st.success(f"已导入 {uploaded.name}")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"导入失败：{exc}")

    # --- Installed plugins ----------------------------------------------
    st.markdown("**Installed Strategies**")
    registrations = manager.list_strategies()
    if not registrations:
        st.info("No strategies installed. Import a ZIP above to get started.")
        return

    headers = st.columns([1.6, 0.6, 0.8, 2.2, 0.7, 1.0, 0.55])
    for cell, name in zip(headers, ("Name", "Version", "Author", "Description",
                                    "Status", "Latest Run", "Actions")):
        cell.caption(name)
    for reg in registrations:
        manifest = reg.manifest
        config = reg.config

        with st.container(border=True):
            cols = st.columns([1.6, 0.6, 0.8, 2.2, 0.7, 1.0, 0.55])
            cols[0].markdown(f"**{manifest.name}**")
            cols[1].write(manifest.version)
            cols[2].write(manifest.author.name)
            description = manifest.description or ""
            cols[3].write(description[:75] + ("…" if len(description) > 75 else ""))
            cols[4].write("已启用" if manager.registry.is_enabled(manifest.id, manifest.version) else "已停用")
            cols[5].write(_latest_run(manager, manifest.id, manifest.version))
            if cols[6].button("Open", key=f"open_{manifest.id}_{manifest.version}"):
                st.session_state["strategies_selected"] = (manifest.id, manifest.version)

    # --- Detail section ---------------------------------------------------
    selected_id = st.session_state.get("strategies_selected")
    if not selected_id:
        return

    selected = next((r for r in registrations
                     if (r.manifest.id, r.manifest.version) == selected_id), None)
    if selected is None:
        st.warning("Selected strategy is no longer installed.")
        return

    manifest = selected.manifest
    config = selected.config

    st.subheader("Detail")

    st.markdown("### Overview")
    st.write(manifest.description or "No description provided.")
    st.markdown(f"**Author:** {manifest.author.name}")
    st.markdown(f"**Version:** {manifest.version}")

    st.markdown("### Parameters")
    params = config.get("parameters", config) if isinstance(config, Mapping) else {}
    if params:
        st.json(params)
    else:
        st.write("No parameters configured.")

    st.markdown("### Required")
    required = manifest.required_features
    if required:
        st.write(", ".join(str(r) for r in required))
    else:
        st.write("None.")

    st.markdown("### Features")
    features = manifest.tags
    if features:
        st.write(", ".join(str(f) for f in features))
    else:
        st.write("None.")

    st.markdown("### Versions")
    runs = manager.store.list_runs(limit=500)
    versions = sorted(
        {
            run["metadata"].get("strategy_version")
            for run in runs
            if (run.get("metadata") or {}).get("strategy_id") == manifest.id
        }
    )
    if versions:
        st.write(", ".join(str(v) for v in versions))
    else:
        st.write("No recorded runs.")

    st.markdown("### Runs")
    strategy_runs = [
        run
        for run in runs
        if (run.get("metadata") or {}).get("strategy_id") == manifest.id
    ]
    if strategy_runs:
        rows = [
            {
                "Version": run["metadata"].get("strategy_version"),
                "Status": run.get("status"),
                "Created At": run.get("created_at"),
            }
            for run in strategy_runs
        ]
        st.dataframe(rows, use_container_width=True)
    else:
        st.write("No runs recorded for this strategy.")


def _latest_run(manager, strategy_id: str, strategy_version: str) -> str:
    """Return a short label for the most recent run of a strategy, else empty."""
    try:
        runs = manager.store.list_runs(limit=500)
    except Exception:  # noqa: BLE001 - non-fatal read
        return ""
    matching = [
        run
        for run in runs
        if (run.get("metadata") or {}).get("strategy_id") == strategy_id
        and (run.get("metadata") or {}).get("strategy_version") == strategy_version
    ]
    if not matching:
        return ""
    latest = max(
        matching,
        key=lambda r: r.get("created_at") or "",
    )
    created = latest.get("created_at")
    return str(created or "").replace("T", " ")[:16] + (" UTC" if created else "")
