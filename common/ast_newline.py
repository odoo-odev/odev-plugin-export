import astunparse
from six.moves import cStringIO


class CustomUnparser(astunparse.Unparser):
    """Customized Unparser to handle NewLine nodes."""

    def _NewLine(self, node):
        self.write(node.unparse())


class NewLine:
    """Custom AST node representing a newline character."""

    def __init__(self):
        pass

    def unparse(self, *, indent="", write=None, add_newline=False):
        """Custom unparsing method to insert a newline."""

        return "\n\n"


def unparse(tree):
    v = cStringIO()
    CustomUnparser(tree, file=v)
    return v.getvalue()
