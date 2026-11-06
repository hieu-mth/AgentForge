import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { theme as antTheme } from 'antd';

// Only a harmless UI preference is stored (never the Owner code or CSRF token).
const KEY = 'agentforge.theme';
const ThemeContext = createContext({mode: 'dark', toggle: () => {}});
export const useThemeMode = () => useContext(ThemeContext);

const initialMode = () => {
  try {
    const saved = window.localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* storage may be blocked */ }
  return 'dark';
};

export function buildTheme(mode) {
  const dark = mode === 'dark';
  return {
    algorithm: dark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
    token: {
      colorPrimary: '#5b5ef4',
      colorInfo: '#5b5ef4',
      colorSuccess: '#16a34a',
      colorWarning: '#f59e0b',
      colorError: '#e5484d',
      colorBgBase: dark ? '#0d0f1a' : '#ffffff',
      colorBgLayout: dark ? '#090b14' : '#f5f6fb',
      colorBgContainer: dark ? '#141729' : '#ffffff',
      colorBgElevated: dark ? '#1a1e33' : '#ffffff',
      colorTextBase: dark ? '#eceefa' : '#171a2e',
      colorBorder: dark ? '#262b45' : '#e4e7f2',
      colorBorderSecondary: dark ? '#202540' : '#edf0f8',
      borderRadius: 10,
      borderRadiusLG: 16,
      fontFamily: 'Inter, "Segoe UI Variable", "Segoe UI", system-ui, -apple-system, sans-serif',
      fontFamilyCode: 'ui-monospace, "Cascadia Code", Consolas, monospace',
      controlHeight: 38,
      motionDurationMid: '.18s',
    },
    components: {
      Layout: {siderBg: '#0f1226', headerBg: 'transparent', bodyBg: dark ? '#090b14' : '#f5f6fb',
        triggerBg: '#0f1226'},
      Menu: {darkItemBg: 'transparent', darkSubMenuItemBg: 'transparent',
        darkItemSelectedBg: 'rgba(124,127,255,.18)', darkItemSelectedColor: '#fff',
        darkItemHoverBg: 'rgba(255,255,255,.06)', darkItemColor: '#a9aed0', itemHeight: 44,
        itemMarginInline: 0, itemBorderRadius: 10},
      Card: {headerFontSize: 15, headerHeight: 54},
      Table: {headerBg: dark ? '#191d33' : '#f8f9fd', headerColor: dark ? '#a9aed0' : '#5d6485',
        headerSplitColor: 'transparent', cellPaddingBlock: 14},
      Tabs: {horizontalItemPadding: '12px 4px', itemColor: dark ? '#9aa0c4' : '#6a7192'},
      Button: {fontWeight: 500, primaryShadow: '0 6px 16px rgba(91,94,244,.28)'},
      Drawer: {colorBgElevated: dark ? '#11142a' : '#ffffff'},
    },
  };
}

export function ThemeProvider({children, render}) {
  const [mode, setMode] = useState(initialMode);
  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    document.querySelector('meta[name="color-scheme"]')?.setAttribute('content', mode);
    try { window.localStorage.setItem(KEY, mode); } catch { /* ignore */ }
  }, [mode]);
  const toggle = useCallback(() => setMode(m => (m === 'dark' ? 'light' : 'dark')), []);
  const value = useMemo(() => ({mode, toggle}), [mode, toggle]);
  return <ThemeContext.Provider value={value}>{render(buildTheme(mode))}</ThemeContext.Provider>;
}
