#!/usr/bin/env python3
"""End-to-end layout migration scenarios against the live Docker API."""
import json
import sys
import urllib.request
import urllib.error

import time

API = "http://localhost:8000"
PASS = 0
FAIL = 0
RUN_ID = str(int(time.time()))


def api(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return {"_error": True, "_status": e.code, "_detail": json.loads(raw)}
        except Exception:
            return {"_error": True, "_status": e.code, "_detail": raw}


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label} — {detail}")


def get_profile(project: str) -> tuple[dict, int]:
    r = api("GET", f"/api/projects/{project}/profile")
    return r["profile"], r["version"]


def plan(project: str, profile: dict, strategy: str = "rename_with_suffix", cleanup: bool = False) -> dict:
    return api("POST", f"/api/projects/{project}/layout/plan", {
        "profile": profile, "strategy": strategy, "cleanup_empty_dirs": cleanup
    })


def apply_plan(project: str, profile: dict, plan_id: str, version: int, strategy: str = "rename_with_suffix", cleanup: bool = False) -> dict:
    return api("POST", f"/api/projects/{project}/layout/apply", {
        "profile": profile, "plan_id": plan_id, "confirm": True,
        "strategy": strategy, "cleanup_empty_dirs": cleanup,
        "if_match_version": version, "updated_by": "e2e-test"
    })


def create_file_in_container(path: str, content: str = "test"):
    """Create a file inside the API container via a small hack: use the initialize + profile to know the root, then use the search API to trigger."""
    import subprocess
    subprocess.run(["docker", "exec", "atlasfile-api", "mkdir", "-p", str(__import__("pathlib").Path(path).parent)], check=True)
    subprocess.run(["docker", "exec", "atlasfile-api", "sh", "-c", f"echo '{content}' > '{path}'"], check=True)


def list_dir_in_container(path: str) -> list[str]:
    import subprocess
    r = subprocess.run(["docker", "exec", "atlasfile-api", "ls", path], capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [x for x in r.stdout.strip().split("\n") if x]


def path_exists_in_container(path: str) -> bool:
    import subprocess
    r = subprocess.run(["docker", "exec", "atlasfile-api", "test", "-e", path], capture_output=True)
    return r.returncode == 0


def init_project(name: str) -> str:
    import subprocess
    subprocess.run(["docker", "exec", "atlasfile-api", "mkdir", "-p", f"/projects/{name}"], check=True)
    r = api("POST", f"/api/projects/{name}/initialize")
    if r.get("_error"):
        print(f"  INIT FAILED: {r}")
    return name


# ═══════════════════════════════════════════════════
print("\n═══ CENÁRIO 1: Sem alteração de layout → 0 ops ═══")
proj = init_project(f"e2e_noop_{RUN_ID}")
p, v = get_profile(proj)
r = plan(proj, p, cleanup=True)
check("status 200", "_error" not in r)
check("ops == 0", r["summary"]["ops"] == 0, f"got {r['summary']['ops']}")
check("moves == 0", r["summary"]["moves"] == 0)
check("conflicts == 0", r["summary"]["conflicts"] == 0)

# ═══════════════════════════════════════════════════
print("\n═══ CENÁRIO 2: Renomear folder com arquivos → moves ═══")
proj = init_project(f"e2e_rename_{RUN_ID}")
p, v = get_profile(proj)
business_domain = p["layout"]["business_domain_folders"][0]["business_domain"]
old_folder = p["layout"]["business_domain_folders"][0]["folder"]
root = f"/projects/{proj}/02_AREAS/{old_folder}"
create_file_in_container(f"{root}/doc1.pdf", "pdf-content")
create_file_in_container(f"{root}/sub/doc2.txt", "text")

new_folder = "renamed_area"
for af in p["layout"]["business_domain_folders"]:
    if af["business_domain"] == business_domain:
        af["folder"] = new_folder

r = plan(proj, p, cleanup=True)
check("status 200", "_error" not in r)
check("moves == 2", r["summary"]["moves"] == 2, f"got {r['summary']['moves']}")
check("mkdirs >= 1", r["summary"]["mkdirs"] >= 1, f"got {r['summary']['mkdirs']}")
check("dsts contain new folder", all(new_folder in (op.get("dst") or "") for op in r["plan"]["ops"] if op["op"] == "move"),
      str([op.get("dst") for op in r["plan"]["ops"] if op["op"] == "move"]))

# Apply
ar = apply_plan(proj, p, r["plan_id"], v, cleanup=True)
check("apply ok", ar.get("ok") is True, str(ar))
check("apply errors == 0", ar.get("apply", {}).get("errors") == 0, str(ar.get("apply")))
check("new folder has doc1.pdf", path_exists_in_container(f"/projects/{proj}/02_AREAS/{new_folder}/doc1.pdf"))
check("new folder has sub/doc2.txt", path_exists_in_container(f"/projects/{proj}/02_AREAS/{new_folder}/sub/doc2.txt"))
check("old folder removed", not path_exists_in_container(f"{root}/doc1.pdf"))

# ═══════════════════════════════════════════════════
print("\n═══ CENÁRIO 3: Remover folder COM conteúdo → conflicts ═══")
proj = init_project(f"e2e_del_content_{RUN_ID}")
p, v = get_profile(proj)
business_domain = p["layout"]["business_domain_folders"][0]["business_domain"]
old_folder = p["layout"]["business_domain_folders"][0]["folder"]
root = f"/projects/{proj}/02_AREAS/{old_folder}"
create_file_in_container(f"{root}/important.pdf", "critical")

p["layout"]["business_domain_folders"] = [
    af
    for af in p["layout"]["business_domain_folders"]
    if af["business_domain"] != business_domain
]

r = plan(proj, p, cleanup=True)
check("status 200", "_error" not in r)
check("conflicts >= 1", r["summary"]["conflicts"] >= 1, f"got {r['summary']['conflicts']}")
conflict_ops = [op for op in r["plan"]["ops"] if op["op"] == "conflict"]
check("conflict op has 'no new folder'", any("no new folder" in op.get("reason", "") for op in conflict_ops),
      str([op.get("reason") for op in conflict_ops]))
check("rmdir_empty for old folder", any(old_folder in (op.get("src") or "") for op in r["plan"]["ops"] if op["op"] == "rmdir_empty") is False,
      "folder with content should NOT be rmdir'd")

# ═══════════════════════════════════════════════════
print("\n═══ CENÁRIO 4: Remover folder VAZIO + cleanup → rmdir_empty ═══")
proj = init_project(f"e2e_del_empty_{RUN_ID}")
p, v = get_profile(proj)
business_domain = p["layout"]["business_domain_folders"][-1]["business_domain"]
old_folder = p["layout"]["business_domain_folders"][-1]["folder"]
remaining_count = len(p["layout"]["business_domain_folders"]) - 1

p["layout"]["business_domain_folders"] = [
    af
    for af in p["layout"]["business_domain_folders"]
    if af["business_domain"] != business_domain
]

r = plan(proj, p, cleanup=True)
check("status 200", "_error" not in r)
rmdir_ops = [op for op in r["plan"]["ops"] if op["op"] == "rmdir_empty"]
check("rmdir_empty >= 1", len(rmdir_ops) >= 1, f"got {len(rmdir_ops)}")
check("rmdir targets old folder", any(old_folder in (op.get("src") or "") for op in rmdir_ops),
      str([op.get("src") for op in rmdir_ops]))
check("remaining folders NOT in rmdir", len(rmdir_ops) <= 2,
      f"got {len(rmdir_ops)} rmdir ops, expected only removed folder(s)")

# Apply
ar = apply_plan(proj, p, r["plan_id"], v, cleanup=True)
check("apply ok", ar.get("ok") is True, str(ar))
check("apply errors == 0", ar.get("apply", {}).get("errors") == 0, str(ar.get("apply")))
check("old folder removed", not path_exists_in_container(f"/projects/{proj}/02_AREAS/{old_folder}"))

# ═══════════════════════════════════════════════════
print("\n═══ CENÁRIO 5: Adicionar novo business_domain folder → mkdir ═══")
proj = init_project(f"e2e_add_{RUN_ID}")
p, v = get_profile(proj)
p["layout"]["business_domain_folders"].append({"business_domain": "novissima", "folder": "99_novissima"})

r = plan(proj, p)
check("status 200", "_error" not in r, str(r.get("_detail", "")))
if "_error" not in r:
    check("mkdirs >= 1", r["summary"]["mkdirs"] >= 1, f"got {r['summary']['mkdirs']}")
    mkdir_ops = [op for op in r["plan"]["ops"] if op["op"] == "mkdir"]
    check("mkdir for novissima", any("novissima" in (op.get("dst") or "") for op in mkdir_ops),
          str([op.get("dst") for op in mkdir_ops]))

    # Apply
    ar = apply_plan(proj, p, r["plan_id"], v)
    check("apply ok", ar.get("ok") is True, str(ar))
    check("new folder created", path_exists_in_container(f"/projects/{proj}/02_AREAS/99_novissima"))
else:
    check("PLAN FAILED - see detail", False, str(r))

# ═══════════════════════════════════════════════════
print("\n═══ CENÁRIO 6: Mudar areas_root → migração completa ═══")
proj = init_project(f"e2e_root_change_{RUN_ID}")
p, v = get_profile(proj)
old_folder = p["layout"]["business_domain_folders"][0]["folder"]
create_file_in_container(f"/projects/{proj}/02_AREAS/{old_folder}/migrar.pdf", "data")

p["layout"]["areas_root"] = "NEW_AREAS"

r = plan(proj, p, cleanup=True)
check("status 200", "_error" not in r)
check("mkdirs >= 1 (new root)", r["summary"]["mkdirs"] >= 1, f"got {r['summary']['mkdirs']}")
check("moves >= 1", r["summary"]["moves"] >= 1, f"got {r['summary']['moves']}")
move_ops = [op for op in r["plan"]["ops"] if op["op"] == "move"]
check("move targets NEW_AREAS", all("NEW_AREAS" in (op.get("dst") or "") for op in move_ops),
      str([op.get("dst") for op in move_ops]))

# Apply
ar = apply_plan(proj, p, r["plan_id"], v, cleanup=True)
check("apply ok", ar.get("ok") is True, str(ar))
check("apply errors == 0", ar.get("apply", {}).get("errors") == 0, str(ar.get("apply")))
check("file in new root", path_exists_in_container(f"/projects/{proj}/NEW_AREAS/{old_folder}/migrar.pdf"))

# ═══════════════════════════════════════════════════
print(f"\n{'='*50}")
print(f"RESULTADO: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
print("TODOS OS CENÁRIOS PASSARAM.")
