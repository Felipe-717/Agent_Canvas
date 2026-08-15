import type { ReactNode } from "react";

/* Iconos de trazo, dibujados a mano para que compartan grosor y esquinas.
 * Una librería entera para ocho iconos sería peso muerto. */

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

export const TrashIcon = () => (
  <Svg>
    <path d="M4 6h12M8 6V4h4v2M6 6l1 10h6l1-10" />
  </Svg>
);

export const PlusIcon = () => (
  <Svg>
    <path d="M10 4v12M4 10h12" />
  </Svg>
);

export const PinIcon = () => (
  <Svg>
    <path d="M4 4h5v5H4zM11 4h5v5h-5zM4 11h5v5H4zM11 11h5v5h-5z" />
  </Svg>
);

export const ChartIcon = () => (
  <Svg>
    <path d="M4 16V9M8 16V4M12 16v-5M16 16v-9" />
  </Svg>
);

export const GridIcon = () => (
  <Svg>
    <path d="M4 4h5v5H4zM11 4h5v5h-5zM4 11h5v5H4zM11 11h5v5h-5z" />
  </Svg>
);

export const TableIcon = () => (
  <Svg>
    <path d="M3 5h14v10H3zM3 9h14M8 9v6" />
  </Svg>
);

export const ChatIcon = () => (
  <Svg>
    <path d="M17 12a2 2 0 0 1-2 2H7l-4 3V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
  </Svg>
);

export const PaperclipIcon = () => (
  <Svg>
    <path d="M15 9l-5.5 5.5a3 3 0 0 1-4.2-4.2L11 4.5a2 2 0 0 1 2.8 2.8l-5.6 5.6a1 1 0 0 1-1.4-1.4L12 6" />
  </Svg>
);

export const SendIcon = () => (
  <Svg>
    <path d="M4 10l12-6-4.5 12L9 11z" />
  </Svg>
);

export const CodeIcon = () => (
  <Svg>
    <path d="M7 6l-3 4 3 4M13 6l3 4-3 4" />
  </Svg>
);

export const RefreshIcon = () => (
  <Svg>
    <path d="M16 10a6 6 0 1 1-1.8-4.3M16 3v3h-3" />
  </Svg>
);
