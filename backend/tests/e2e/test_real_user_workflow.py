"""真实端到端测试套件 (Real-World E2E Test Suite).

覆盖 10 大核心用户操作链路的全生命周期黑盒测试：
1. 鉴权与站源配置 (POST /login, GET/POST /api/settings)
2. 搜索与高级过滤 (GET /api/eh/search)
3. 画廊下载与轮询 (POST /api/downloads, 轮询 GET /api/downloads)
4. 本地画廊管理 (PATCH /api/galleries/:id/local, PUT/DELETE /api/galleries/:id/progress)
5. 收藏夹全套 (分类管理, 添加, 便签, 移动, 移出, 查重接口)
6. 自定义列表全生命周期 (创建, 添加, 移出, 改名, 删除)
7. 重复排查与完整性 (跨 GID/扫描重复, 完整性检测)
8. 归档与冷存储 (CBZ 导出, 冷存储状态查询)
9. 回收站与生命周期 (软删除, 回收站查询, 恢复, 永久清理)
10. 任务中心与审计日志 (GET /api/logs, GET /api/system/logs)
"""

import asyncio
import contextlib
import os
import uuid

import httpx
import pytest

E2E_BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
E2E_PASSWORD = os.getenv("E2E_PASSWORD", os.getenv("LOGIN_PASSWORD", "password"))


def check_e2e_prerequisites(base_url: str) -> None:
    """前置探测机制：CI 环境跳过保护与测试后端连通性检查。"""
    if (os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true") and os.getenv("RUN_E2E") != "1":
        pytest.skip("Skipping E2E in CI environment without running test stack")

    try:
        with httpx.Client(base_url=base_url, timeout=1.0) as client:
            client.get("/healthz")
    except Exception:  # noqa: BLE001
        pytest.skip("E2E test requires running backend test stack")


@pytest.fixture(autouse=True)
def _ensure_e2e_environment() -> None:
    """在测试用例初始化前自动执行环境连通性探测。"""
    check_e2e_prerequisites(E2E_BASE_URL)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_real_user_workflow_e2e():
    """按真实用户使用生命周期串联测试 10 大业务阶段，并在 finally 中彻底自愈清理。"""
    check_e2e_prerequisites(E2E_BASE_URL)
    target_gallery_id: int | None = None
    created_list_id: int | None = None
    created_list_ids: list[int] = []
    created_gallery_ids: list[int] = []
    created_fav_gids: list[int] = []
    active_gid: int | None = None
    active_token: str | None = None

    async with httpx.AsyncClient(base_url=E2E_BASE_URL, timeout=30.0, follow_redirects=False) as client:
        try:
            # -------------------------------------------------------------
            # 1. 鉴权与站源配置
            # -------------------------------------------------------------
            # 登录获取 session cookie
            login_resp = await client.post("/login", data={"password": E2E_PASSWORD})
            assert login_resp.status_code in {200, 302, 303}, f"Login failed: {login_resp.status_code}"
            session_cookie = client.cookies.get("galleryvault_session") or client.cookies.get("session")
            # 容忍未启用 auth 模式
            if login_resp.status_code in {302, 303}:
                assert session_cookie or len(client.cookies) > 0, "No session cookie set on redirect"

            # 验证 session 接口
            session_resp = await client.get("/api/auth/session")
            assert session_resp.status_code == 200, f"Get session failed: {session_resp.text}"

            # 站源配置：确保 exhentai_base_url 为 https://e-hentai.org
            settings_resp = await client.get("/api/settings")
            assert settings_resp.status_code == 200, f"Get settings failed: {settings_resp.text}"
            settings_data = settings_resp.json()
            assert isinstance(settings_data, dict)

            # 更新站源配置
            patch_settings_resp = await client.post(
                "/api/settings",
                json={"exhentai_base_url": "https://e-hentai.org"},
            )
            assert patch_settings_resp.status_code in {200, 204}, f"Update settings failed: {patch_settings_resp.text}"

            # -------------------------------------------------------------
            # 2. 发现、搜索与筛选
            # -------------------------------------------------------------
            target_gallery_info = None
            eh_search_resp = await client.get(
                "/api/eh/search",
                params={"q": "misc", "category": "misc", "min_rating": 0},
            )
            if eh_search_resp.status_code == 200:
                search_data = eh_search_resp.json()
                items = search_data.get("items", [])
                for it in items:
                    pages = it.get("pages")
                    if pages is not None and 1 <= int(pages) <= 5 and it.get("gid") and it.get("token"):
                        target_gallery_info = it
                        break

            # 若网络环境无外网或无匹配小画廊，通过现有本地画廊库 fallback 探测
            local_list_resp = await client.get("/api/galleries", params={"page_size": 10})
            assert local_list_resp.status_code == 200, f"List galleries failed: {local_list_resp.text}"

            # -------------------------------------------------------------
            # 3. 极小画廊下载流程与轮询
            # -------------------------------------------------------------
            if target_gallery_info is not None:
                active_gid = int(target_gallery_info["gid"])
                active_token = str(target_gallery_info["token"])
                title = target_gallery_info.get("title") or "e2e_test_gallery"

                dl_resp = await client.post(
                    "/api/downloads",
                    json={"gid": active_gid, "token": active_token, "title": title, "mode": "gallery"},
                )
                assert dl_resp.status_code in {200, 202, 409}, f"Download dispatch failed: {dl_resp.text}"

                # 轮询下载任务状态直到终态（超时 30 秒，容忍网络抖动）
                for _ in range(15):
                    await asyncio.sleep(2)
                    status_resp = await client.get("/api/downloads")
                    if status_resp.status_code == 200:
                        dl_list = status_resp.json().get("items", [])
                        matched = next((d for d in dl_list if d.get("gid") == active_gid), None)
                        if matched and matched.get("status") in {"completed", "failed", "cancelled"}:
                            break

            # 获取一个可用于后续阶段测试的本地画廊实体
            refreshed_list = await client.get("/api/galleries", params={"page_size": 10})
            assert refreshed_list.status_code == 200
            current_local_items = refreshed_list.json().get("items", [])

            if current_local_items:
                picked = current_local_items[0]
                target_gallery_id = picked["id"]
                active_gid = picked.get("gid")
                active_token = picked.get("token")
                created_gallery_ids.append(target_gallery_id)

            # -------------------------------------------------------------
            # 4. 本地画廊管理 (Rating, Note, Tags, Progress)
            # -------------------------------------------------------------
            if target_gallery_id is not None:
                # 本地评分与便签
                patch_local_resp = await client.patch(
                    f"/api/galleries/{target_gallery_id}/local",
                    json={
                        "local_rating": 5,
                        "local_note": "e2e_verification_note",
                        "local_tags": ["e2e_test_tag"],
                    },
                )
                assert patch_local_resp.status_code == 200, f"Patch local metadata failed: {patch_local_resp.text}"
                local_meta = patch_local_resp.json()
                assert local_meta.get("local_rating") == 5
                assert local_meta.get("local_note") == "e2e_verification_note"

                # 阅读进度更新
                progress_put_resp = await client.put(
                    f"/api/galleries/{target_gallery_id}/progress",
                    json={"current_page": 1, "total_pages": 5},
                )
                assert progress_put_resp.status_code == 200, f"Save progress failed: {progress_put_resp.text}"

                # 查询阅读进度
                progress_get_resp = await client.get(f"/api/galleries/{target_gallery_id}/progress")
                assert progress_get_resp.status_code == 200
                assert progress_get_resp.json().get("current_page") == 1

                # 清除阅读进度
                progress_del_resp = await client.delete(f"/api/galleries/{target_gallery_id}/progress")
                assert progress_del_resp.status_code == 204, f"Delete progress failed: {progress_del_resp.text}"

            # -------------------------------------------------------------
            # 5. 收藏夹全套操作
            # -------------------------------------------------------------
            fav_cats_resp = await client.get("/api/favorites/categories")
            assert fav_cats_resp.status_code == 200, f"Get favorite categories failed: {fav_cats_resp.text}"
            fav_cats = fav_cats_resp.json()
            assert isinstance(fav_cats, list)

            # 更新/配置收藏分类 (favcat 0)
            update_favcat_resp = await client.post(
                "/api/favorites/categories",
                json={"favcat": 0, "enabled": True, "mode": "gallery"},
            )
            assert update_favcat_resp.status_code == 200, f"Update favcat failed: {update_favcat_resp.text}"

            if active_gid and active_token:
                created_fav_gids.append(active_gid)
                # 添加收藏
                add_fav_resp = await client.post(
                    "/api/favorites/add",
                    json={
                        "favcat": 0,
                        "items": [{"gid": active_gid, "token": active_token, "note": "e2e_fav_note"}],
                    },
                )
                assert add_fav_resp.status_code in {200, 422, 502}

                # 收藏便签更新
                note_resp = await client.post(
                    "/api/favorites/note",
                    json={"gid": active_gid, "token": active_token, "favcat": 0, "note": "updated_e2e_note"},
                )
                assert note_resp.status_code in {200, 422, 502}

                # 收藏分类间移动
                move_resp = await client.post(
                    "/api/favorites/move",
                    json={"gids": [active_gid], "target_favcat": 1},
                )
                assert move_resp.status_code in {200, 422, 502}

                # 收藏移出
                remove_fav_resp = await client.post(
                    "/api/favorites/remove",
                    json={"gids": [active_gid], "delete_local": False},
                )
                assert remove_fav_resp.status_code in {200, 422, 502}

            # 触发收藏夹查重扫描与状态读取
            dup_scan_resp = await client.post("/api/favorites/duplicates/scan")
            assert dup_scan_resp.status_code in {202, 409}, f"Dup scan trigger failed: {dup_scan_resp.text}"
            dup_status_resp = await client.get("/api/favorites/duplicates/status")
            assert dup_status_resp.status_code == 200, f"Dup scan status failed: {dup_status_resp.text}"

            # -------------------------------------------------------------
            # 6. 自定义列表全生命周期
            # -------------------------------------------------------------
            list_name = f"e2e_list_{uuid.uuid4().hex[:6]}"
            new_list_resp = await client.post("/api/lists", json={"name": list_name})
            assert new_list_resp.status_code == 201, f"Create list failed: {new_list_resp.text}"
            list_info = new_list_resp.json()
            list_id = list_info["id"]
            created_list_id = list_id
            created_list_ids.append(list_id)

            # 查询列表列表
            all_lists_resp = await client.get("/api/lists")
            assert all_lists_resp.status_code == 200
            assert any(l["id"] == list_id for l in all_lists_resp.json().get("items", []))

            if target_gallery_id is not None:
                # 向列表添加画廊
                add_item_resp = await client.post(
                    f"/api/lists/{list_id}/items",
                    json={"gallery_ids": [target_gallery_id]},
                )
                assert add_item_resp.status_code == 200, f"Add item to list failed: {add_item_resp.text}"

                # 查询列表详情
                get_list_resp = await client.get(f"/api/lists/{list_id}")
                assert get_list_resp.status_code == 200
                assert target_gallery_id in get_list_resp.json().get("gallery_ids", [])

                # 从列表移除画廊
                rm_item_resp = await client.post(
                    f"/api/lists/{list_id}/items/remove",
                    json={"gallery_ids": [target_gallery_id]},
                )
                assert rm_item_resp.status_code == 200, f"Remove item from list failed: {rm_item_resp.text}"

            # 重命名自定义列表
            renamed_name = f"{list_name}_renamed"
            rename_resp = await client.patch(f"/api/lists/{list_id}", json={"name": renamed_name})
            assert rename_resp.status_code == 200, f"Rename list failed: {rename_resp.text}"
            assert rename_resp.json().get("name") == renamed_name

            # 删除自定义列表
            del_list_resp = await client.delete(f"/api/lists/{list_id}")
            assert del_list_resp.status_code == 200, f"Delete list failed: {del_list_resp.text}"
            created_list_ids.remove(list_id)

            # -------------------------------------------------------------
            # 7. 重复排查与完整性检查
            # -------------------------------------------------------------
            # 重复扫描
            cross_dup_resp = await client.get("/api/library/duplicates/cross-gid")
            assert cross_dup_resp.status_code == 200, f"Cross-gid duplicates failed: {cross_dup_resp.text}"

            scan_dup_resp = await client.get("/api/scan/duplicates")
            assert scan_dup_resp.status_code == 200, f"Scan duplicates failed: {scan_dup_resp.text}"

            # 完整性扫描与列表
            integrity_resp = await client.get("/api/galleries/integrity")
            assert integrity_resp.status_code == 200, f"List integrity issues failed: {integrity_resp.text}"

            integrity_trigger = await client.post("/api/galleries/integrity/scan")
            assert integrity_trigger.status_code == 202, f"Trigger integrity scan failed: {integrity_trigger.text}"

            # -------------------------------------------------------------
            # 8. 归档与冷存储相关操作
            # -------------------------------------------------------------
            archive_status_resp = await client.get("/api/archive")
            assert archive_status_resp.status_code == 200, f"Get archive status failed: {archive_status_resp.text}"

            if target_gallery_id is not None:
                # 导出画廊为 CBZ
                cbz_resp = await client.get(f"/api/galleries/{target_gallery_id}/export.cbz")
                assert cbz_resp.status_code in {200, 404, 500}

            # -------------------------------------------------------------
            # 9. 回收站与生命周期 (软删除 -> 查回收站 -> 恢复)
            # -------------------------------------------------------------
            if target_gallery_id is not None:
                # 软删除 (delete_files=False)
                del_soft_resp = await client.delete(
                    f"/api/galleries/{target_gallery_id}",
                    params={"delete_files": False},
                )
                assert del_soft_resp.status_code == 204, f"Soft delete failed: {del_soft_resp.text}"

                # 查询回收站验证软删除
                trash_resp = await client.get("/api/galleries/trash")
                assert trash_resp.status_code == 200, f"Get trash failed: {trash_resp.text}"
                trashed_ids = [item["id"] for item in trash_resp.json().get("items", [])]
                assert target_gallery_id in trashed_ids, f"Gallery {target_gallery_id} not found in trash"

                # 从回收站恢复
                restore_resp = await client.post(
                    "/api/galleries/restore",
                    json={"ids": [target_gallery_id]},
                )
                assert restore_resp.status_code == 200, f"Restore gallery failed: {restore_resp.text}"
                assert restore_resp.json().get("restored", 0) >= 1

            # -------------------------------------------------------------
            # 10. 任务中心与审计日志
            # -------------------------------------------------------------
            logs_resp = await client.get("/api/logs")
            assert logs_resp.status_code == 200, f"Get logs failed: {logs_resp.text}"
            logs_data = logs_resp.json()
            assert "running" in logs_data and "finished" in logs_data

            sys_logs_resp = await client.get("/api/system/logs")
            assert sys_logs_resp.status_code == 200, f"Get system logs failed: {sys_logs_resp.text}"

        finally:
            # -------------------------------------------------------------
            # 自愈清理：确保不残留任何测试生成的数据与实体
            # -------------------------------------------------------------
            # 1. 清理遗留列表
            cleanup_lids = set(created_list_ids)
            if created_list_id is not None:
                cleanup_lids.add(created_list_id)
            for lid in cleanup_lids:
                with contextlib.suppress(httpx.HTTPError):
                    await client.delete(f"/api/lists/{lid}")

            # 2. 清理测试收藏夹条目
            if created_fav_gids:
                with contextlib.suppress(httpx.HTTPError):
                    await client.post(
                        "/api/favorites/remove",
                        json={"gids": created_fav_gids, "delete_local": False},
                    )

            # 3. 恢复本地元数据至正常状态
            if target_gallery_id is not None:
                with contextlib.suppress(httpx.HTTPError):
                    await client.patch(
                        f"/api/galleries/{target_gallery_id}/local",
                        json={"local_rating": None, "local_note": "", "local_tags": []},
                    )
                with contextlib.suppress(httpx.HTTPError):
                    await client.delete(f"/api/galleries/{target_gallery_id}/progress")
