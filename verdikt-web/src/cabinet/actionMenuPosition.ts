interface Anchor {left: number; right: number; top: number; bottom: number; width: number}
interface Viewport {width: number; height: number}

/** Position measured menus within the viewport while keeping a gap from their trigger. */
export function actionMenuPosition(anchor: Anchor, viewport: Viewport, menuHeight: number, placement: 'auto' | 'above' = 'auto', matchWidth = false) {
  const margin = 8;
  const width = Math.min(matchWidth ? anchor.width : 210, Math.max(0, viewport.width - margin * 2));
  const maxHeight = Math.max(0, viewport.height - margin * 2);
  const height = Math.min(menuHeight, maxHeight);
  const above = anchor.top - margin - height;
  const below = anchor.bottom + margin;
  const preferAbove = placement === 'above' ? above >= margin || below + height > viewport.height - margin : below + height > viewport.height - margin;
  return {
    left: Math.max(margin, Math.min(matchWidth ? anchor.left : anchor.right - width, viewport.width - margin - width)),
    top: Math.max(margin, Math.min(preferAbove ? above : below, viewport.height - margin - height)),
    width, maxHeight,
  };
}
