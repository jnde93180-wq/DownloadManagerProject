def register(manager):
    print("Example plugin loaded. Current item count:", len(manager.items))
    # example: register hooks
    def on_added(item):
        print(f"[plugin] item added: {getattr(item, 'url', None)}")

    def on_progress(item):
        print(f"[plugin] progress {getattr(item, 'id', None)}: {getattr(item, 'progress', None):.1f}%")

    try:
        manager.register_hook('on_item_added', on_added)
        manager.register_hook('on_item_progress', on_progress)
    except Exception:
        pass
