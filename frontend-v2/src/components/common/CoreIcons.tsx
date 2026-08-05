import React from 'react';

export const XrayIcon: React.FC<{ className?: string }> = ({ className = 'w-4 h-4' }) => (
  <svg viewBox="0 0 24 24" className={className} fill="currentColor">
    <path d="M 11,1 C 9.5,7 7,9.5 1,11 L 11,11 Z M 13,1 L 13,11 L 23,11 C 17,9.5 14.5,7 13,1 Z M 13,23 C 14.5,17 17,14.5 23,13 L 13,13 Z M 11,23 L 11,13 L 1,13 C 7,14.5 9.5,17 11,23 Z" />
  </svg>
);

export const HysteriaIcon: React.FC<{ className?: string }> = ({ className = 'w-4 h-4' }) => (
  <svg viewBox="0 0 442.19 323.31" className={className}>
    <polygon fill="currentColor" points="72.8 140.45 60.1 285.55 102.51 285.55 111.5 182.86 111.54 182.86 115.21 140.45 72.8 140.45" />
    <polygon fill="currentColor" points="124.16 37.75 81.76 37.75 76.19 101.36 118.59 101.36 124.16 37.75" />
    <polygon fill="currentColor" points="318.36 285.56 360.44 285.56 366.01 221.95 323.9 221.95 318.36 285.56" />
    <polygon fill="currentColor" points="382.09 37.76 340 37.76 329.16 161.66 221.09 161.66 206.95 323.31 292.78 201.84 438.67 201.84 442.19 161.66 371.25 161.66 382.09 37.76" />
    <polygon fill="#ffbc00" points="149.41 121.47 3.52 121.47 0 161.66 221.09 161.66 235.23 0 149.41 121.47" />
  </svg>
);

export const SingboxIcon: React.FC<{ className?: string }> = ({ className = 'w-4 h-4' }) => (
  <svg viewBox="0 0 24 24" className={className}>
    <path d="M12 2.5 C12.6 2.5 13.2 2.8 13.8 3.1 L20.5 6.5 C21.4 7.0 21.6 7.8 21.2 8.5 L12 13.2 L2.8 8.5 C2.4 7.8 2.6 7.0 3.5 6.5 L10.2 3.1 C10.8 2.8 11.4 2.5 12 2.5 Z" fill="#546E7A" />
    <path d="M2.8 8.5 L12 13.2 V20.5 C12 21.3 11.3 21.9 10.5 21.5 L3.8 18.2 C2.9 17.7 2.4 16.8 2.4 15.8 V9.5 C2.4 8.9 2.5 8.6 2.8 8.5 Z" fill="#37474F" />
    <path d="M12 13.2 L21.2 8.5 C21.5 8.6 21.6 8.9 21.6 9.5 V15.8 C21.6 16.8 21.1 17.7 20.2 18.2 L13.5 21.5 C12.7 21.9 12 21.3 12 20.5 V13.2 Z" fill="#263238" />
    <path d="M6.5 4.7 L9.8 3.0 C10.2 3.2 10.6 3.4 11.0 3.6 L18.5 10.2 L15.2 11.8 L6.5 4.7 Z" fill="#ECEFF1" />
    <path d="M18.5 10.2 L18.5 14.5 C18.5 15.2 17.8 15.6 17.2 15.3 L15.2 14.2 V11.8 L18.5 10.2 Z" fill="#CFD8DC" />
  </svg>
);

export const SpectreLogoImg: React.FC<{ className?: string }> = ({ className = 'w-9 h-9' }) => (
  <img
    src="./img/logo.svg"
    alt="Spectre Logo"
    className={`${className} filter drop-shadow-[0_4px_12px_rgba(124,58,237,0.4)] transition-transform duration-300 hover:scale-105`}
  />
);
