/**
 * XFold fold mark — prefers the brand SVG from `/brand/`.
 * Falls back to a tiny inline stroke if the asset fails to load.
 */
export function FoldMark({
  className = "",
  size = 28,
}: {
  className?: string;
  size?: number;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/brand/xfold-mark-primary.svg"
      alt=""
      width={size}
      height={size}
      className={className}
      draggable={false}
    />
  );
}

/** Horizontal wordmark for wider chrome (sidebar branding). */
export function FoldLogo({
  className = "",
  width = 140,
}: {
  className?: string;
  width?: number;
}) {
  const height = Math.round((width * 96) / 320);
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/brand/xfold-logo-primary.svg"
      alt="XFold"
      width={width}
      height={height}
      className={className}
      draggable={false}
    />
  );
}
