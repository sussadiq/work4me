import Gio from 'gi://Gio';

const IFACE_XML = `
<node>
  <interface name="com.work4me.WindowFocus">
    <method name="ActivateByWmClass">
      <arg name="wm_class" type="s" direction="in" />
      <arg name="found" type="b" direction="out" />
    </method>
    <method name="ActivateByWmClassAndTitle">
      <arg name="wm_class" type="s" direction="in" />
      <arg name="title_substring" type="s" direction="in" />
      <arg name="found" type="b" direction="out" />
    </method>
  </interface>
</node>`;

export default class Work4MeFocusExtension {
    #dbus;

    enable() {
        this.#dbus = Gio.DBusExportedObject.wrapJSObject(IFACE_XML, this);
        this.#dbus.export(Gio.DBus.session, '/com/work4me/WindowFocus');
    }

    disable() {
        this.#dbus?.unexport_from_connection(Gio.DBus.session);
        this.#dbus = undefined;
    }

    ActivateByWmClass(wm_class) {
        for (const actor of global.get_window_actors()) {
            const win = actor.get_meta_window();
            if (win.get_wm_class() === wm_class) {
                const ws = win.get_workspace();
                const now = global.get_current_time();
                ws ? ws.activate_with_focus(win, now) : win.activate(now);
                return true;
            }
        }
        return false;
    }

    ActivateByWmClassAndTitle(wm_class, title_substring) {
        const wm_lower = wm_class.toLowerCase();
        let fallback = null;

        for (const actor of global.get_window_actors()) {
            const win = actor.get_meta_window();
            if (win.get_wm_class()?.toLowerCase() !== wm_lower)
                continue;

            // First match by WM_CLASS kept as fallback
            if (!fallback)
                fallback = win;

            const title = win.get_title() || '';
            if (title.includes(title_substring)) {
                const ws = win.get_workspace();
                const now = global.get_current_time();
                ws ? ws.activate_with_focus(win, now) : win.activate(now);
                return true;
            }
        }

        // Fallback: activate first WM_CLASS match (never worse than before)
        if (fallback) {
            const ws = fallback.get_workspace();
            const now = global.get_current_time();
            ws ? ws.activate_with_focus(fallback, now) : fallback.activate(now);
            return true;
        }

        return false;
    }
}
