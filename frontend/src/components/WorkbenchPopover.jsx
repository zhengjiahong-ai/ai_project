import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { MoreHorizontal } from 'lucide-react';
import './WorkbenchPopover.css';

/** Non-modal popover. Forms use normal Tab order; Escape returns focus to the trigger.
 * @param {{label: string, trigger?: import('react').ReactNode, children: import('react').ReactNode | ((close: (restore?: boolean) => void) => import('react').ReactNode), className?: string, align?: string, disabled?: boolean}} props
 */
export default function WorkbenchPopover({ label, trigger = null, children, className = '', align = 'right', disabled = false }) {
  const [open, setOpen] = useState(false);
  const [closeEpoch, setCloseEpoch] = useState(0);
  const root = useRef(null), button = useRef(null), panel = useRef(null);
  const id = useId();
  const [position, setPosition] = useState({ top: 0, left: 0 });
  useLayoutEffect(() => {
    if (!open || !button.current || !panel.current) return;
    const place = () => {
      const anchor = button.current.getBoundingClientRect();
      const width = panel.current.offsetWidth, height = panel.current.offsetHeight;
      const top = anchor.bottom + 6 + height <= window.innerHeight - 8 ? anchor.bottom + 6 : anchor.top - height - 6;
      setPosition({ top: Math.max(8, Math.min(top, window.innerHeight - height - 8)),
        left: Math.max(8, Math.min(align === 'left' ? anchor.left : anchor.right - width, window.innerWidth - width - 8)) });
    };
    place(); window.addEventListener('resize', place); window.addEventListener('scroll', place, true);
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(place) : null;
    observer?.observe(panel.current);
    return () => { window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true); observer?.disconnect(); };
  }, [open, align, children]);
  const close = (restore = true) => { setOpen(false); if (restore) setCloseEpoch(value => value + 1); };
  useEffect(() => { if (closeEpoch) button.current?.focus(); }, [closeEpoch]);
  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector('input, button:not(:disabled), select, summary')?.focus();
    const outside = event => { if (!root.current?.contains(event.target)) setOpen(false); };
    const escape = event => { if (event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); event.stopPropagation(); setOpen(false); button.current?.focus(); } };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [open]);
  return <div ref={root} className={`workbench-popover ${className}`} onBlur={event => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }}>
    <button ref={button} type="button" className="workbench-popover-trigger" aria-label={label} title={label}
      aria-expanded={open} aria-controls={id} disabled={disabled} onClick={() => setOpen(value => !value)}>
      {trigger || <MoreHorizontal size={18} />}
    </button>
    {open && <div ref={panel} id={id} style={position} className={`workbench-popover-panel align-${align}`} role="dialog" aria-label={label}>
      {typeof children === 'function' ? children(close) : children}
    </div>}
  </div>;
}
