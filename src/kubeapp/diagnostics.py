"""Concise CLI presentation of structured Helm mapping diagnostics."""

from kubeapp.value_mapping import MappingResult, MappingStatus


def helm_messages(mapping: MappingResult) -> tuple[str, ...]:
    messages = []
    for note in mapping.capability_notes:
        messages.append(
            f'WARNING: Application capability "{note.capability}" could not be mapped: '
            f'no detectable {note.expected_kind} capability in the supplied chart.'
        )
    shown = set()
    for diagnostic in sorted(mapping.diagnostics, key=lambda item: (len(item.generated_path), item.generated_path)):
        path, status = diagnostic.generated_path, diagnostic.status
        if status == MappingStatus.SUPPORTED:
            continue
        # A parent warning/note also covers its descendants with the same status.
        if any((path[:length], status) in shown for length in range(1, len(path) + 1)):
            continue
        shown.add((path, status))
        label = ".".join(path)
        if status == MappingStatus.UNSUPPORTED:
            messages.append(f'WARNING: Generated value path "{label}" is not declared by the supplied '
                            "chart's values contract; check the chart's expected keys. Value retained.")
        else:
            messages.append(f'NOTE: Chart support for generated value path "{label}" could not be '
                            "determined from its values contract. Value retained.")
    return tuple(dict.fromkeys(messages))
