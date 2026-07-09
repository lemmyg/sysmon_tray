import sys
from AppKit import NSApplication, NSStatusBar, NSVariableStatusItemLength, NSApplicationActivationPolicyAccessory
app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
bar = NSStatusBar.systemStatusBar()
item = bar.statusItemWithLength_(NSVariableStatusItemLength)
print("item:", item)
sys.stdout.flush()
