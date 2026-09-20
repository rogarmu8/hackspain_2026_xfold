import type { ReactElement, ReactNode } from "react";
import { colors } from "./theme";

type IconProps = { size?: number; color?: string };

const svg = (size: number, color: string, path: ReactNode): ReactElement => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 64 64"
    fill="none"
    stroke={color}
    strokeWidth="3.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {path}
  </svg>
);

export const IconPeople: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <>
      <circle cx="22" cy="20" r="7" />
      <path d="M8 48c2-10 8-14 14-14s12 4 14 14" />
      <circle cx="44" cy="22" r="6" />
      <path d="M36 48c1-8 5-12 8-12 4 0 9 4 12 12" />
    </>,
  );

export const IconClock: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <>
      <circle cx="32" cy="32" r="18" />
      <path d="M32 20v13l9 6" />
    </>,
  );

export const IconShirt: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <path d="M22 12h6l4 6 4-6h6l10 8-6 6v24H18V26l-6-6z" />,
  );

export const IconCoin: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <>
      <circle cx="32" cy="32" r="18" />
      <path d="M38 24c-2-2-5-3-8-3-7 0-10 4-10 8s4 6 10 7 10 3 10 8-4 8-11 8c-4 0-7-1-9-3" />
      <path d="M32 16v4M32 44v4" />
    </>,
  );

export const IconPlace: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <>
      <path d="M20 12h6l6 6 6-6h6l8 7-5 5v14H17V25l-5-6z" />
      <path d="M10 50h44" />
    </>,
  );

export const IconIron: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <path d="M10 42h36c6 0 10-5 10-10H22c-6 0-10 4-12 10zM18 22h16" />,
  );

export const IconFold: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <path d="M16 12h32v40H16zM32 12v40M16 32h16" />,
  );

export const IconBox: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <path d="M8 22l24-10 24 10v28L32 60 8 50V22zM8 22l24 10 24-10M32 32v28" />,
  );

export const IconHotel: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <path d="M10 54V18l22-8 22 8v36H10zM24 54V36h16v18M22 28h4M38 28h4" />,
  );

export const IconCart: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <>
      <path d="M8 12h8l6 28h24l8-20H22" />
      <circle cx="28" cy="50" r="4" />
      <circle cx="46" cy="50" r="4" />
    </>,
  );

export const IconTag: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <path d="M12 36l20 16 20-28-12-12-28 12zM40 16l8 8" />,
  );

export const IconFactory: React.FC<IconProps> = ({
  size = 72,
  color = colors.orange,
}) =>
  svg(
    size,
    color,
    <path d="M8 54V30l16 10V30l16 10V22h16v32H8zM44 16c4-6 8-6 12 0" />,
  );

export const IconChevron: React.FC<IconProps> = ({
  size = 40,
  color = colors.orange,
}) =>
  svg(size, color, <path d="M22 16l16 16-16 16" />);
