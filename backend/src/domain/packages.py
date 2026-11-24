"""Shared-work-order grouping for package-level actual minutes.

Some lectures are reviewed together as a package and only the package total
actual minutes are recorded. Packages that share a work order belong to one
group (transitive closure via union-find). The analysis never allocates a
package total back to individual work orders: every group is treated as a
single observation whose feature vector is the sum of its member rows.
"""


class _UnionFind:
    def __init__(self):
        self._parent = {}

    def find(self, key):
        self._parent.setdefault(key, key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, left, right):
        root_left, root_right = self.find(left), self.find(right)
        if root_left != root_right:
            self._parent[root_right] = root_left


def _package_declarations(rows):
    """Map package id to the rows and declared total carried by the CSV."""
    declarations = {}
    for index, row in enumerate(rows):
        package_id = row.get("package_id")
        if not package_id:
            continue
        declaration = declarations.setdefault(package_id, {"rows": [], "totals": set()})
        declaration["rows"].append(index)
        total = row.get("package_actual_minutes")
        if total is not None:
            declaration["totals"].add(total)
    return declarations


def build_groups(rows, corrections=None):
    """Build package groups and validate their declared actual minutes.

    Returns a dict with:
      groups: list of dicts (key, member row indexes, package ids, actual total)
      row_group: row index -> group key (None for rows outside any package)
      correction_by_package: package id -> latest correction record
      conflict_notes: validation messages about clashing declared totals
    """
    corrections = corrections or []
    declarations = _package_declarations(rows)
    finder = _UnionFind()

    # Packages sharing a work order merge into one group.
    job_to_packages = {}
    for package_id, declaration in declarations.items():
        finder.find(package_id)
        for row_index in declaration["rows"]:
            job_id = rows[row_index]["job_id"]
            job_to_packages.setdefault(job_id, []).append(package_id)
    for package_ids in job_to_packages.values():
        for package_id in package_ids[1:]:
            finder.union(package_ids[0], package_id)

    conflict_notes = []
    for package_id, declaration in declarations.items():
        if len(declaration["totals"]) > 1:
            totals = "、".join(f"{value:g}" for value in sorted(declaration["totals"]))
            conflict_notes.append(f"包 {package_id} 的整包实耗声明不一致（{totals} 分钟），请先更正后再回测")

    latest_by_package = {}
    for correction in corrections:
        package_id = correction["package_id"]
        previous = latest_by_package.get(package_id)
        if previous is None or (correction["created_at"], correction["id"]) > (
            previous["created_at"], previous["id"]
        ):
            latest_by_package[package_id] = correction

    merged = {}
    for package_id, declaration in declarations.items():
        key = finder.find(package_id)
        group = merged.setdefault(key, {"key": key, "row_indexes": [], "package_ids": set(),
                                        "declared": set(), "correction": None})
        group["row_indexes"].extend(declaration["rows"])
        group["package_ids"].add(package_id)
        group["declared"].update(declaration["totals"])

    groups = []
    for group in merged.values():
        group["row_indexes"] = sorted(set(group["row_indexes"]))
        group["package_ids"] = sorted(group["package_ids"])
        package_corrections = [latest_by_package[pid] for pid in group["package_ids"]
                               if pid in latest_by_package]
        correction = max(package_corrections,
                         key=lambda item: (item["created_at"], item["id"]), default=None)
        if len(group["declared"]) > 1:
            actual = None
        elif correction is not None:
            actual = correction["actual_minutes"]
        else:
            actual = next(iter(group["declared"]), None)
        group["actual_minutes"] = actual
        group["correction"] = correction
        group["has_conflict"] = len(group["declared"]) > 1
        groups.append(group)

    groups.sort(key=lambda item: item["key"])
    row_group = {}
    for group in groups:
        for row_index in group["row_indexes"]:
            row_group[row_index] = group["key"]
    return {"groups": groups, "row_group": row_group,
            "correction_by_package": latest_by_package, "conflict_notes": conflict_notes}


def observations(rows, groups):
    """Aggregate each group into one observation: summed features + total target."""
    aggregated = []
    for group in groups:
        members = [rows[index] for index in group["row_indexes"]]
        record = {
            "key": group["key"],
            "package_ids": tuple(group["package_ids"]),
            "job_ids": tuple(member["job_id"] for member in members),
            "job_date": min(member["job_date"] for member in members),
            "last_date": max(member["job_date"] for member in members),
            "titles": tuple(member["title"] for member in members),
            "actual_minutes": group["actual_minutes"],
            "correction": group["correction"],
            "has_conflict": group["has_conflict"],
        }
        for field_name in ("video_minutes", "low_confidence_pct", "speaker_changes", "term_count"):
            record[field_name] = sum(member[field_name] for member in members)
        aggregated.append(record)
    return aggregated
