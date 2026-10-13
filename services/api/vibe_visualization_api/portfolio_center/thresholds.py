"""User-defined net-asset amount thresholds, not unit NAV or trading orders."""


def compile_nav_thresholds(nav, scenarios, warning_line, floor):
    rows = []
    for label, value in [('持仓快照（未施加冲击）', nav), *[(s['label'], s['stressNav']) for s in scenarios]]:
        if value is None:
            status = 'unassessed'
        elif warning_line is None and floor is None:
            status = 'unconfigured'
        elif floor is not None and value < floor:
            status = 'floor_breached'
        elif floor is not None and value == floor:
            status = 'floor_reached'
        elif warning_line is not None and value <= warning_line:
            status = 'warning'
        else:
            status = 'above_lines'
        rows.append(dict(label=label, nav=value, status=status,
                         warningHeadroom=value-warning_line if value is not None and warning_line is not None else None,
                         floorHeadroom=value-floor if value is not None and floor is not None else None))
    return dict(warningLine=warning_line, floor=floor, rows=rows)
