/* Iconos de trazo, dibujados a mano para que compartan grosor y esquinas.
 * Una libreria entera para seis iconos seria peso muerto. */

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function Svg({ children }: { children: React.ReactNode }) {
  return (
    <svg width="16" height="16" viewBox="0 0 20 20" {...stroke}>
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
    <path d="M7 3h6l-1 5 3 3H5l3-3-1-5zM10 11v6" />
  </Svg>
);

export const UploadIcon = () => (
  <Svg>
    <path d="M10 14V4M6 8l4-4 4 4M4 15v2h12v-2" />
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
