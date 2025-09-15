from django import forms


def _get_cf_for_model(field_names, model):
    """
    Return the CustomField instance attached to `model` whose name is in field_names.
    Works with NetBox 4.4's `object_types` (e.g., 'dcim.device', 'virtualization.virtualmachine').
    """
    try:
        from extras.models import CustomField

        model_label = f"{model._meta.app_label}.{model._meta.model_name}"
        # Try any of the candidate names
        for name in field_names:
            cf = CustomField.objects.filter(name=name).first()
            if not cf:
                continue
            obj_types = getattr(cf, "object_types", []) or []
            if model_label in obj_types:
                return cf
        return None
    except Exception:
        return None


def _choices_from_choice_set(cf):
    """Return [(value,label), ...] from cf.choice_set, or [] if none."""
    if not cf or not getattr(cf, "choice_set", None):
        return []
    try:
        return [
            (str(ch.value), ch.label)
            for ch in cf.choice_set.choices.all().order_by("weight", "label")
        ]
    except Exception:
        # Fallback to arrays if present
        base = list(getattr(cf.choice_set, "base_choices", []) or [])
        extra = list(getattr(cf.choice_set, "extra_choices", []) or [])
        out = []
        for pair in base + extra:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                out.append((str(pair[0]), pair[1]))
        return out


class ExtraTemplatesForm(forms.Form):
    """
    Dynamic form that renders `zb_extra_templates` as a select or multi-select,
    using the CF's choice set for options.
    """

    def __init__(self, *args, obj=None, **kwargs):
        super().__init__(*args, **kwargs)
        assert obj is not None, "ExtraTemplatesForm requires obj=<Device|VM>"

        # Find the CF on this model. Try common names.
        cf = _get_cf_for_model(
            field_names=("zb_extra_templates", "zb_extra_template_list"),
            model=obj,
        )

        # Pull choices. If no CF found, fall back to primary template choice set (optional).
        choices = _choices_from_choice_set(cf)
        if not choices:
            from extras.models import CustomField

            cf2 = CustomField.objects.filter(name="zb_primary_template_list").first()
            if cf2:
                choices = _choices_from_choice_set(cf2)

        # Detect CF type: single vs multiple selection
        cf_type = getattr(cf, "type", None) if cf else None
        is_multi = str(cf_type) in {"multi-select", "multiselect", "select_multiple"}

        field_cls = forms.MultipleChoiceField if is_multi else forms.ChoiceField
        self.fields["extra_templates"] = field_cls(
            required=False,
            choices=choices,
            label="Extra Templates",
            help_text=(
                "Select one or more additional Zabbix templates to apply."
                if is_multi
                else "Select an additional Zabbix template."
            ),
        )
        # Style for NetBox/Bootstrap tables
        self.fields["extra_templates"].widget.attrs.update(
            {
                "class": "form-select",
                "size": str(min(len(choices), 10) if choices else 5),
            }
        )

        # Initial value from the object's CF data (handles list, CSV, or empty)
        data = getattr(obj, "custom_field_data", {}) or {}
        current = data.get("zb_extra_templates")
        if isinstance(current, str):
            current = [s.strip() for s in current.replace("\n", ",").split(",") if s.strip()]
        if current is None:
            current = []
        if is_multi:
            self.initial["extra_templates"] = [str(x) for x in current]
        else:
            self.initial["extra_templates"] = (
                str(current[0])
                if isinstance(current, list) and current
                else (str(current) if current else "")
            )
