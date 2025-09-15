from netbox.plugins import PluginTemplateExtension


class _NoOp(PluginTemplateExtension):
    models = []

    def right_page(self):
        return ""
