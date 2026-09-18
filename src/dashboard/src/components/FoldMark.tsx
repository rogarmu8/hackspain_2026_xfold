export function FoldMark({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M3 16.5V4.5L10 8.2L17 4.5V16.5L10 12.8L3 16.5Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M10 8.2V12.8" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
