from typing import Dict, List, Optional, Tuple

from core.mission import (
    apply_loiter_edit,
    apply_table_cell_edit,
    build_upload_confirmation_message,
    build_import_success_message,
    prepare_import_preview,
    process_imported_waypoints,
    resolve_delete_selection,
    split_downloaded_waypoints,
    uniform_height_default,
    validate_uniform_height_value,
)


class WaypointPanelController:
    def handle_loiter_changed(self, row: int, is_loiter: bool, total_rows: int, mission_waypoints: List[Dict]) -> Tuple[Optional[List[Dict]], Optional[str]]:
        return apply_loiter_edit(row, is_loiter, total_rows, mission_waypoints)

    def handle_table_item_changed(self, row: int, column: int, text: str, total_rows: int, mission_waypoints: List[Dict]) -> Tuple[Optional[List[Dict]], Optional[str]]:
        return apply_table_cell_edit(row, column, text, total_rows, mission_waypoints)

    def build_upload_confirm_message(self, mission_count: int) -> str:
        return build_upload_confirmation_message(mission_count)

    def handle_download_result(self, success: bool, downloaded: Optional[List[Dict]], message: str) -> Tuple[Optional[Dict], List[Dict], Optional[str]]:
        if not success:
            return None, [], message or "未知错误"
        if downloaded is None:
            return None, [], "下载结果为空"
        home_wp, mission_waypoints = split_downloaded_waypoints(downloaded)
        return home_wp, mission_waypoints, None

    def handle_delete_selected(self, selected_rows: List[int], total_rows: int) -> Tuple[List[int], bool]:
        return resolve_delete_selection(selected_rows, total_rows)

    def default_uniform_height(self, mission_waypoints: List[Dict]) -> float:
        return uniform_height_default(mission_waypoints)

    def validate_uniform_height(self, height: float) -> bool:
        return validate_uniform_height_value(height)

    def build_import_preview(self, imported_waypoints: List[Dict]) -> Tuple[List[Dict], int, int, str]:
        return prepare_import_preview(imported_waypoints)

    def handle_imported_waypoints(self, valid_waypoints: List[Dict], home_wp: Optional[Dict]) -> Tuple[Optional[Dict], Dict, List[Dict], int]:
        return process_imported_waypoints(valid_waypoints, home_wp)

    def build_import_success_message(self, mission_count: int, has_overrides: bool, has_home: bool) -> str:
        return build_import_success_message(mission_count, has_overrides, has_home)
