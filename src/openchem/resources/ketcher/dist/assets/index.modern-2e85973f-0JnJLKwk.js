import { s as styled, a as styleFunctionSx, r as reactExports, u as useTheme, e as extendSxProp, b as _objectWithoutPropertiesLoose, j as jsxRuntimeExports, c as _extends$1, g as generateUtilityClass, d as generateUtilityClasses, f as useDefaultProps, h as clsx$1, i as capitalize, k as composeClasses, l as styled$1, C as ClassNameGenerator, T as THEME_ID, m as createTheme, B as ButtonGroupContext, n as ButtonGroupButtonContext, o as colorManipulatorExports, p as useTheme$1, P as Paper, F as Fade, q as useId, M as Modal$1, t as Backdrop, L as ListContext, v as getListItemTextUtilityClass, w as listItemTextClasses, x as hasOwn, E as Emotion$1, y as createEmotionProps, z as getDefaultExportFromCjs, A as lodashExports, G as Global, D as EditorClassName, H as ThemeProvider, I as Provider_default, J as css, K as _slicedToArray, N as createStyled, O as Fe, S as SetEditorLineLengthAction, Q as Snackbar, U as SettingsManager, V as _defineProperty$1, W as CoreEditor, X as RenderersManager, Y as useDispatch, Z as useSelector, $ as ketcherProvider, a0 as KetcherLogger, a1 as KetcherAsyncEvents, a2 as _toConsumableArray, R as React__default, a3 as SequenceType, a4 as IconButton, a5 as ZoomTool, a6 as Icon, a7 as KETCHER_MACROMOLECULES_ROOT_NODE_SELECTOR, a8 as HydrogenBond, a9 as calculateBondPreviewPosition, aa as BackBoneSequenceNode, ab as AmbiguousMonomer, ac as LinkerSequenceNode, ad as Nucleotide, ae as Nucleoside, af as clsx$2, ag as Vec2, ah as Coordinates, ai as AmbiguousMonomerPreview, aj as isLibraryItemRnaPreset, ak as isTwoStrandedNodeRestrictedForHydrogenBondCreation, al as reactDomExports, am as isPlainObject$1, an as combineReducers, ao as applyMiddleware, ap as createStore, aq as isAmbiguousMonomerLibraryItem, ar as setAmbiguousMonomerTemplatePrefix, as as setMonomerTemplatePrefix, at as monomerFactory, au as KetMonomerClass, av as buildRnaPresetConnections, aw as getRnaPresetPhosphatePosition, ax as useInView, ay as _objectWithoutProperties, az as ArrowScroll, aA as DEFAULT_LAYOUT_MODE, aB as HAS_CONTENT_LAYOUT_MODE, aC as generateMenuShortcuts, aD as hotkeysConfiguration, aE as RNABase, aF as getSugarFromRnaBase2, aG as isSugarOrAmbiguousSugar, aH as getRnaBaseFromSugar, aI as Sugar, aJ as isRnaBaseOrAmbiguousRnaBase2, aK as _asyncToGenerator, aL as _regeneratorRuntime, aM as Button, aN as _typeof, aO as Button$1, aP as getFullscreenElement, aQ as Popover, aR as createSelector, aS as ToolName, aT as SnakeLayoutCellWidth, aU as Atom, aV as BaseMonomer, aW as SelectBase, aX as Input$2, aY as notifyRequestCompleted, aZ as Struct, a_ as IndigoProvider, a$ as KetSerializer, b0 as ChainsCollection, b1 as getAllConnectedMonomersRecursively, b2 as UsageInMacromolecule, b3 as preview, b4 as AmbiguousMonomerRenderer, b5 as Entities, b6 as Peptide, b7 as canModifyAminoAcid, b8 as getAminoAcidsToModify, b9 as compareByTitleWithNaturalFirst, ba as SequenceRenderer, bb as EmptySequenceNode, bc as ChemicalMimeType$1, bd as isHelmCompatible, be as getSvgFromDrawnStructures, bf as useTheme$2, bg as IconButton$1, bh as compose, bi as MONOMER_CONST, bj as _createClass, bk as MonomerToAtomBond, bl as RNA_DNA_NON_MODIFIED_PART, bm as KetAmbiguousMonomerTemplateSubType, bn as peptideNaturalAnalogues, bo as rnaDnaNaturalAnalogues, bp as StructRender, bq as Phosphate, br as provideEditorInstance, bs as A, bt as Kt, bu as pt, bv as Et, bw as it, bx as FileSaver_minExports, by as isClipboardAPIAvailable, bz as legacyCopy, bA as EditorHistory, bB as ButtonBase, bC as thunk, bD as withExtraArgument, bE as _classCallCheck, bF as MonomerGroups$1, bG as Tabs$2, bH as Tab, bI as MenuItem$1, bJ as Select, bK as FormControl, bL as Tooltip, bM as tooltipClasses, bN as normalizeError, bO as macromoleculesFilesInputFormats, bP as isAction, bQ as calculateAmbiguousMonomerPreviewTop, bR as calculateMonomerPreviewTop, bS as calculateNucleoElementPreviewTop, bT as useDropzone, bU as ModeTypes, bV as libraryItemHasR1AttachmentPoint, bW as Accordion$1, bX as Collapse, bY as usePortalStyle, bZ as ClickAwayListener } from './index-CVzMPpWP.js';

function r(e){var t,f,n="";if("string"==typeof e||"number"==typeof e)n+=e;else if("object"==typeof e)if(Array.isArray(e)){var o=e.length;for(t=0;t<o;t++)e[t]&&(f=r(e[t]))&&(n&&(n+=" "),n+=f);}else for(f in e)e[f]&&(n&&(n+=" "),n+=f);return n}function clsx(){for(var e,t,f=0,n="",o=arguments.length;f<o;f++)(e=arguments[f])&&(t=r(e))&&(n&&(n+=" "),n+=t);return n}

const _excluded$c = ["className", "component"];
function createBox(options = {}) {
  const {
    themeId,
    defaultTheme,
    defaultClassName = 'MuiBox-root',
    generateClassName
  } = options;
  const BoxRoot = styled('div', {
    shouldForwardProp: prop => prop !== 'theme' && prop !== 'sx' && prop !== 'as'
  })(styleFunctionSx);
  const Box = /*#__PURE__*/reactExports.forwardRef(function Box(inProps, ref) {
    const theme = useTheme(defaultTheme);
    const _extendSxProp = extendSxProp(inProps),
      {
        className,
        component = 'div'
      } = _extendSxProp,
      other = _objectWithoutPropertiesLoose(_extendSxProp, _excluded$c);
    return /*#__PURE__*/jsxRuntimeExports.jsx(BoxRoot, _extends$1({
      as: component,
      ref: ref,
      className: clsx(className, generateClassName ? generateClassName(defaultClassName) : defaultClassName),
      theme: themeId ? theme[themeId] || theme : theme
    }, other));
  });
  return Box;
}

/**
 * Gets only the valid children of a component,
 * and ignores any nullish or falsy child.
 *
 * @param children the children
 */
function getValidReactChildren(children) {
  return reactExports.Children.toArray(children).filter(child => /*#__PURE__*/reactExports.isValidElement(child));
}

function getTypographyUtilityClass(slot) {
  return generateUtilityClass('MuiTypography', slot);
}
generateUtilityClasses('MuiTypography', ['root', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'subtitle1', 'subtitle2', 'body1', 'body2', 'inherit', 'button', 'caption', 'overline', 'alignLeft', 'alignRight', 'alignCenter', 'alignJustify', 'noWrap', 'gutterBottom', 'paragraph']);

const _excluded$b = ["align", "className", "component", "gutterBottom", "noWrap", "paragraph", "variant", "variantMapping"];
const useUtilityClasses$6 = (ownerState) => {
  const {
    align,
    gutterBottom,
    noWrap,
    paragraph,
    variant,
    classes
  } = ownerState;
  const slots = {
    root: ["root", variant, ownerState.align !== "inherit" && `align${capitalize(align)}`, gutterBottom && "gutterBottom", noWrap && "noWrap", paragraph && "paragraph"]
  };
  return composeClasses(slots, getTypographyUtilityClass, classes);
};
const TypographyRoot = styled$1("span", {
  name: "MuiTypography",
  slot: "Root",
  overridesResolver: (props, styles) => {
    const {
      ownerState
    } = props;
    return [styles.root, ownerState.variant && styles[ownerState.variant], ownerState.align !== "inherit" && styles[`align${capitalize(ownerState.align)}`], ownerState.noWrap && styles.noWrap, ownerState.gutterBottom && styles.gutterBottom, ownerState.paragraph && styles.paragraph];
  }
})(({
  theme,
  ownerState
}) => _extends$1({
  margin: 0
}, ownerState.variant === "inherit" && {
  // Some elements, like <button> on Chrome have default font that doesn't inherit, reset this.
  font: "inherit"
}, ownerState.variant !== "inherit" && theme.typography[ownerState.variant], ownerState.align !== "inherit" && {
  textAlign: ownerState.align
}, ownerState.noWrap && {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap"
}, ownerState.gutterBottom && {
  marginBottom: "0.35em"
}, ownerState.paragraph && {
  marginBottom: 16
}));
const defaultVariantMapping = {
  h1: "h1",
  h2: "h2",
  h3: "h3",
  h4: "h4",
  h5: "h5",
  h6: "h6",
  subtitle1: "h6",
  subtitle2: "h6",
  body1: "p",
  body2: "p",
  inherit: "p"
};
const colorTransformations = {
  primary: "primary.main",
  textPrimary: "text.primary",
  secondary: "secondary.main",
  textSecondary: "text.secondary",
  error: "error.main"
};
const transformDeprecatedColors = (color) => {
  return colorTransformations[color] || color;
};
const Typography = /* @__PURE__ */ reactExports.forwardRef(function Typography2(inProps, ref) {
  const themeProps = useDefaultProps({
    props: inProps,
    name: "MuiTypography"
  });
  const color = transformDeprecatedColors(themeProps.color);
  const props = extendSxProp(_extends$1({}, themeProps, {
    color
  }));
  const {
    align = "inherit",
    className,
    component,
    gutterBottom = false,
    noWrap = false,
    paragraph = false,
    variant = "body1",
    variantMapping = defaultVariantMapping
  } = props, other = _objectWithoutPropertiesLoose(props, _excluded$b);
  const ownerState = _extends$1({}, props, {
    align,
    color,
    className,
    component,
    gutterBottom,
    noWrap,
    paragraph,
    variant,
    variantMapping
  });
  const Component = component || (paragraph ? "p" : variantMapping[variant] || defaultVariantMapping[variant]) || "span";
  const classes = useUtilityClasses$6(ownerState);
  return /* @__PURE__ */ jsxRuntimeExports.jsx(TypographyRoot, _extends$1({
    as: Component,
    ref,
    ownerState,
    className: clsx$1(classes.root, className)
  }, other));
});

const boxClasses = generateUtilityClasses('MuiBox', ['root']);

const defaultTheme$1 = createTheme();
const Box = createBox({
  themeId: THEME_ID,
  defaultTheme: defaultTheme$1,
  defaultClassName: boxClasses.root,
  generateClassName: ClassNameGenerator.generate
});

function getButtonGroupUtilityClass(slot) {
  return generateUtilityClass('MuiButtonGroup', slot);
}
const buttonGroupClasses = generateUtilityClasses('MuiButtonGroup', ['root', 'contained', 'outlined', 'text', 'disableElevation', 'disabled', 'firstButton', 'fullWidth', 'vertical', 'grouped', 'groupedHorizontal', 'groupedVertical', 'groupedText', 'groupedTextHorizontal', 'groupedTextVertical', 'groupedTextPrimary', 'groupedTextSecondary', 'groupedOutlined', 'groupedOutlinedHorizontal', 'groupedOutlinedVertical', 'groupedOutlinedPrimary', 'groupedOutlinedSecondary', 'groupedContained', 'groupedContainedHorizontal', 'groupedContainedVertical', 'groupedContainedPrimary', 'groupedContainedSecondary', 'lastButton', 'middleButton']);

const _excluded$a = ["children", "className", "color", "component", "disabled", "disableElevation", "disableFocusRipple", "disableRipple", "fullWidth", "orientation", "size", "variant"];
const overridesResolver = (props, styles) => {
  const {
    ownerState
  } = props;
  return [{
    [`& .${buttonGroupClasses.grouped}`]: styles.grouped
  }, {
    [`& .${buttonGroupClasses.grouped}`]: styles[`grouped${capitalize(ownerState.orientation)}`]
  }, {
    [`& .${buttonGroupClasses.grouped}`]: styles[`grouped${capitalize(ownerState.variant)}`]
  }, {
    [`& .${buttonGroupClasses.grouped}`]: styles[`grouped${capitalize(ownerState.variant)}${capitalize(ownerState.orientation)}`]
  }, {
    [`& .${buttonGroupClasses.grouped}`]: styles[`grouped${capitalize(ownerState.variant)}${capitalize(ownerState.color)}`]
  }, {
    [`& .${buttonGroupClasses.firstButton}`]: styles.firstButton
  }, {
    [`& .${buttonGroupClasses.lastButton}`]: styles.lastButton
  }, {
    [`& .${buttonGroupClasses.middleButton}`]: styles.middleButton
  }, styles.root, styles[ownerState.variant], ownerState.disableElevation === true && styles.disableElevation, ownerState.fullWidth && styles.fullWidth, ownerState.orientation === "vertical" && styles.vertical];
};
const useUtilityClasses$5 = (ownerState) => {
  const {
    classes,
    color,
    disabled,
    disableElevation,
    fullWidth,
    orientation,
    variant
  } = ownerState;
  const slots = {
    root: ["root", variant, orientation === "vertical" && "vertical", fullWidth && "fullWidth", disableElevation && "disableElevation"],
    grouped: ["grouped", `grouped${capitalize(orientation)}`, `grouped${capitalize(variant)}`, `grouped${capitalize(variant)}${capitalize(orientation)}`, `grouped${capitalize(variant)}${capitalize(color)}`, disabled && "disabled"],
    firstButton: ["firstButton"],
    lastButton: ["lastButton"],
    middleButton: ["middleButton"]
  };
  return composeClasses(slots, getButtonGroupUtilityClass, classes);
};
const ButtonGroupRoot = styled$1("div", {
  name: "MuiButtonGroup",
  slot: "Root",
  overridesResolver
})(({
  theme,
  ownerState
}) => _extends$1({
  display: "inline-flex",
  borderRadius: (theme.vars || theme).shape.borderRadius
}, ownerState.variant === "contained" && {
  boxShadow: (theme.vars || theme).shadows[2]
}, ownerState.disableElevation && {
  boxShadow: "none"
}, ownerState.fullWidth && {
  width: "100%"
}, ownerState.orientation === "vertical" && {
  flexDirection: "column"
}, {
  [`& .${buttonGroupClasses.grouped}`]: _extends$1({
    minWidth: 40,
    "&:hover": _extends$1({}, ownerState.variant === "contained" && {
      boxShadow: "none"
    })
  }, ownerState.variant === "contained" && {
    boxShadow: "none"
  }),
  [`& .${buttonGroupClasses.firstButton},& .${buttonGroupClasses.middleButton}`]: _extends$1({}, ownerState.orientation === "horizontal" && {
    borderTopRightRadius: 0,
    borderBottomRightRadius: 0
  }, ownerState.orientation === "vertical" && {
    borderBottomRightRadius: 0,
    borderBottomLeftRadius: 0
  }, ownerState.variant === "text" && ownerState.orientation === "horizontal" && {
    borderRight: theme.vars ? `1px solid rgba(${theme.vars.palette.common.onBackgroundChannel} / 0.23)` : `1px solid ${theme.palette.mode === "light" ? "rgba(0, 0, 0, 0.23)" : "rgba(255, 255, 255, 0.23)"}`,
    [`&.${buttonGroupClasses.disabled}`]: {
      borderRight: `1px solid ${(theme.vars || theme).palette.action.disabled}`
    }
  }, ownerState.variant === "text" && ownerState.orientation === "vertical" && {
    borderBottom: theme.vars ? `1px solid rgba(${theme.vars.palette.common.onBackgroundChannel} / 0.23)` : `1px solid ${theme.palette.mode === "light" ? "rgba(0, 0, 0, 0.23)" : "rgba(255, 255, 255, 0.23)"}`,
    [`&.${buttonGroupClasses.disabled}`]: {
      borderBottom: `1px solid ${(theme.vars || theme).palette.action.disabled}`
    }
  }, ownerState.variant === "text" && ownerState.color !== "inherit" && {
    borderColor: theme.vars ? `rgba(${theme.vars.palette[ownerState.color].mainChannel} / 0.5)` : colorManipulatorExports.alpha(theme.palette[ownerState.color].main, 0.5)
  }, ownerState.variant === "outlined" && ownerState.orientation === "horizontal" && {
    borderRightColor: "transparent"
  }, ownerState.variant === "outlined" && ownerState.orientation === "vertical" && {
    borderBottomColor: "transparent"
  }, ownerState.variant === "contained" && ownerState.orientation === "horizontal" && {
    borderRight: `1px solid ${(theme.vars || theme).palette.grey[400]}`,
    [`&.${buttonGroupClasses.disabled}`]: {
      borderRight: `1px solid ${(theme.vars || theme).palette.action.disabled}`
    }
  }, ownerState.variant === "contained" && ownerState.orientation === "vertical" && {
    borderBottom: `1px solid ${(theme.vars || theme).palette.grey[400]}`,
    [`&.${buttonGroupClasses.disabled}`]: {
      borderBottom: `1px solid ${(theme.vars || theme).palette.action.disabled}`
    }
  }, ownerState.variant === "contained" && ownerState.color !== "inherit" && {
    borderColor: (theme.vars || theme).palette[ownerState.color].dark
  }, {
    "&:hover": _extends$1({}, ownerState.variant === "outlined" && ownerState.orientation === "horizontal" && {
      borderRightColor: "currentColor"
    }, ownerState.variant === "outlined" && ownerState.orientation === "vertical" && {
      borderBottomColor: "currentColor"
    })
  }),
  [`& .${buttonGroupClasses.lastButton},& .${buttonGroupClasses.middleButton}`]: _extends$1({}, ownerState.orientation === "horizontal" && {
    borderTopLeftRadius: 0,
    borderBottomLeftRadius: 0
  }, ownerState.orientation === "vertical" && {
    borderTopRightRadius: 0,
    borderTopLeftRadius: 0
  }, ownerState.variant === "outlined" && ownerState.orientation === "horizontal" && {
    marginLeft: -1
  }, ownerState.variant === "outlined" && ownerState.orientation === "vertical" && {
    marginTop: -1
  })
}));
const ButtonGroup = /* @__PURE__ */ reactExports.forwardRef(function ButtonGroup2(inProps, ref) {
  const props = useDefaultProps({
    props: inProps,
    name: "MuiButtonGroup"
  });
  const {
    children,
    className,
    color = "primary",
    component = "div",
    disabled = false,
    disableElevation = false,
    disableFocusRipple = false,
    disableRipple = false,
    fullWidth = false,
    orientation = "horizontal",
    size = "medium",
    variant = "outlined"
  } = props, other = _objectWithoutPropertiesLoose(props, _excluded$a);
  const ownerState = _extends$1({}, props, {
    color,
    component,
    disabled,
    disableElevation,
    disableFocusRipple,
    disableRipple,
    fullWidth,
    orientation,
    size,
    variant
  });
  const classes = useUtilityClasses$5(ownerState);
  const context = reactExports.useMemo(() => ({
    className: classes.grouped,
    color,
    disabled,
    disableElevation,
    disableFocusRipple,
    disableRipple,
    fullWidth,
    size,
    variant
  }), [color, disabled, disableElevation, disableFocusRipple, disableRipple, fullWidth, size, variant, classes.grouped]);
  const validChildren = getValidReactChildren(children);
  const childrenCount = validChildren.length;
  const getButtonPositionClassName = (index) => {
    const isFirstButton = index === 0;
    const isLastButton = index === childrenCount - 1;
    if (isFirstButton && isLastButton) {
      return "";
    }
    if (isFirstButton) {
      return classes.firstButton;
    }
    if (isLastButton) {
      return classes.lastButton;
    }
    return classes.middleButton;
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsx(ButtonGroupRoot, _extends$1({
    as: component,
    role: "group",
    className: clsx$1(classes.root, className),
    ref,
    ownerState
  }, other, {
    children: /* @__PURE__ */ jsxRuntimeExports.jsx(ButtonGroupContext.Provider, {
      value: context,
      children: validChildren.map((child, index) => {
        return /* @__PURE__ */ jsxRuntimeExports.jsx(ButtonGroupButtonContext.Provider, {
          value: getButtonPositionClassName(index),
          children: child
        }, index);
      })
    })
  }));
});

function getDialogUtilityClass(slot) {
  return generateUtilityClass('MuiDialog', slot);
}
const dialogClasses = generateUtilityClasses('MuiDialog', ['root', 'scrollPaper', 'scrollBody', 'container', 'paper', 'paperScrollPaper', 'paperScrollBody', 'paperWidthFalse', 'paperWidthXs', 'paperWidthSm', 'paperWidthMd', 'paperWidthLg', 'paperWidthXl', 'paperFullWidth', 'paperFullScreen']);

const DialogContext = /* @__PURE__ */ reactExports.createContext({});

const _excluded$9 = ["aria-describedby", "aria-labelledby", "BackdropComponent", "BackdropProps", "children", "className", "disableEscapeKeyDown", "fullScreen", "fullWidth", "maxWidth", "onBackdropClick", "onClick", "onClose", "open", "PaperComponent", "PaperProps", "scroll", "TransitionComponent", "transitionDuration", "TransitionProps"];
const DialogBackdrop = styled$1(Backdrop, {
  name: "MuiDialog",
  slot: "Backdrop",
  overrides: (props, styles) => styles.backdrop
})({
  // Improve scrollable dialog support.
  zIndex: -1
});
const useUtilityClasses$4 = (ownerState) => {
  const {
    classes,
    scroll,
    maxWidth,
    fullWidth,
    fullScreen
  } = ownerState;
  const slots = {
    root: ["root"],
    container: ["container", `scroll${capitalize(scroll)}`],
    paper: ["paper", `paperScroll${capitalize(scroll)}`, `paperWidth${capitalize(String(maxWidth))}`, fullWidth && "paperFullWidth", fullScreen && "paperFullScreen"]
  };
  return composeClasses(slots, getDialogUtilityClass, classes);
};
const DialogRoot = styled$1(Modal$1, {
  name: "MuiDialog",
  slot: "Root",
  overridesResolver: (props, styles) => styles.root
})({
  "@media print": {
    // Use !important to override the Modal inline-style.
    position: "absolute !important"
  }
});
const DialogContainer = styled$1("div", {
  name: "MuiDialog",
  slot: "Container",
  overridesResolver: (props, styles) => {
    const {
      ownerState
    } = props;
    return [styles.container, styles[`scroll${capitalize(ownerState.scroll)}`]];
  }
})(({
  ownerState
}) => _extends$1({
  height: "100%",
  "@media print": {
    height: "auto"
  },
  // We disable the focus ring for mouse, touch and keyboard users.
  outline: 0
}, ownerState.scroll === "paper" && {
  display: "flex",
  justifyContent: "center",
  alignItems: "center"
}, ownerState.scroll === "body" && {
  overflowY: "auto",
  overflowX: "hidden",
  textAlign: "center",
  "&::after": {
    content: '""',
    display: "inline-block",
    verticalAlign: "middle",
    height: "100%",
    width: "0"
  }
}));
const DialogPaper = styled$1(Paper, {
  name: "MuiDialog",
  slot: "Paper",
  overridesResolver: (props, styles) => {
    const {
      ownerState
    } = props;
    return [styles.paper, styles[`scrollPaper${capitalize(ownerState.scroll)}`], styles[`paperWidth${capitalize(String(ownerState.maxWidth))}`], ownerState.fullWidth && styles.paperFullWidth, ownerState.fullScreen && styles.paperFullScreen];
  }
})(({
  theme,
  ownerState
}) => _extends$1({
  margin: 32,
  position: "relative",
  overflowY: "auto",
  // Fix IE11 issue, to remove at some point.
  "@media print": {
    overflowY: "visible",
    boxShadow: "none"
  }
}, ownerState.scroll === "paper" && {
  display: "flex",
  flexDirection: "column",
  maxHeight: "calc(100% - 64px)"
}, ownerState.scroll === "body" && {
  display: "inline-block",
  verticalAlign: "middle",
  textAlign: "left"
  // 'initial' doesn't work on IE11
}, !ownerState.maxWidth && {
  maxWidth: "calc(100% - 64px)"
}, ownerState.maxWidth === "xs" && {
  maxWidth: theme.breakpoints.unit === "px" ? Math.max(theme.breakpoints.values.xs, 444) : `max(${theme.breakpoints.values.xs}${theme.breakpoints.unit}, 444px)`,
  [`&.${dialogClasses.paperScrollBody}`]: {
    [theme.breakpoints.down(Math.max(theme.breakpoints.values.xs, 444) + 32 * 2)]: {
      maxWidth: "calc(100% - 64px)"
    }
  }
}, ownerState.maxWidth && ownerState.maxWidth !== "xs" && {
  maxWidth: `${theme.breakpoints.values[ownerState.maxWidth]}${theme.breakpoints.unit}`,
  [`&.${dialogClasses.paperScrollBody}`]: {
    [theme.breakpoints.down(theme.breakpoints.values[ownerState.maxWidth] + 32 * 2)]: {
      maxWidth: "calc(100% - 64px)"
    }
  }
}, ownerState.fullWidth && {
  width: "calc(100% - 64px)"
}, ownerState.fullScreen && {
  margin: 0,
  width: "100%",
  maxWidth: "100%",
  height: "100%",
  maxHeight: "none",
  borderRadius: 0,
  [`&.${dialogClasses.paperScrollBody}`]: {
    margin: 0,
    maxWidth: "100%"
  }
}));
const Dialog = /* @__PURE__ */ reactExports.forwardRef(function Dialog2(inProps, ref) {
  const props = useDefaultProps({
    props: inProps,
    name: "MuiDialog"
  });
  const theme = useTheme$1();
  const defaultTransitionDuration = {
    enter: theme.transitions.duration.enteringScreen,
    exit: theme.transitions.duration.leavingScreen
  };
  const {
    "aria-describedby": ariaDescribedby,
    "aria-labelledby": ariaLabelledbyProp,
    BackdropComponent,
    BackdropProps,
    children,
    className,
    disableEscapeKeyDown = false,
    fullScreen = false,
    fullWidth = false,
    maxWidth = "sm",
    onBackdropClick,
    onClick,
    onClose,
    open,
    PaperComponent = Paper,
    PaperProps = {},
    scroll = "paper",
    TransitionComponent = Fade,
    transitionDuration = defaultTransitionDuration,
    TransitionProps
  } = props, other = _objectWithoutPropertiesLoose(props, _excluded$9);
  const ownerState = _extends$1({}, props, {
    disableEscapeKeyDown,
    fullScreen,
    fullWidth,
    maxWidth,
    scroll
  });
  const classes = useUtilityClasses$4(ownerState);
  const backdropClick = reactExports.useRef();
  const handleMouseDown = (event) => {
    backdropClick.current = event.target === event.currentTarget;
  };
  const handleBackdropClick = (event) => {
    if (onClick) {
      onClick(event);
    }
    if (!backdropClick.current) {
      return;
    }
    backdropClick.current = null;
    if (onBackdropClick) {
      onBackdropClick(event);
    }
    if (onClose) {
      onClose(event, "backdropClick");
    }
  };
  const ariaLabelledby = useId(ariaLabelledbyProp);
  const dialogContextValue = reactExports.useMemo(() => {
    return {
      titleId: ariaLabelledby
    };
  }, [ariaLabelledby]);
  return /* @__PURE__ */ jsxRuntimeExports.jsx(DialogRoot, _extends$1({
    className: clsx$1(classes.root, className),
    closeAfterTransition: true,
    components: {
      Backdrop: DialogBackdrop
    },
    componentsProps: {
      backdrop: _extends$1({
        transitionDuration,
        as: BackdropComponent
      }, BackdropProps)
    },
    disableEscapeKeyDown,
    onClose,
    open,
    ref,
    onClick: handleBackdropClick,
    ownerState
  }, other, {
    children: /* @__PURE__ */ jsxRuntimeExports.jsx(TransitionComponent, _extends$1({
      appear: true,
      in: open,
      timeout: transitionDuration,
      role: "presentation"
    }, TransitionProps, {
      children: /* @__PURE__ */ jsxRuntimeExports.jsx(DialogContainer, {
        className: clsx$1(classes.container),
        onMouseDown: handleMouseDown,
        ownerState,
        children: /* @__PURE__ */ jsxRuntimeExports.jsx(DialogPaper, _extends$1({
          as: PaperComponent,
          elevation: 24,
          role: "dialog",
          "aria-describedby": ariaDescribedby,
          "aria-labelledby": ariaLabelledby
        }, PaperProps, {
          className: clsx$1(classes.paper, PaperProps.className),
          ownerState,
          children: /* @__PURE__ */ jsxRuntimeExports.jsx(DialogContext.Provider, {
            value: dialogContextValue,
            children
          })
        }))
      })
    }))
  }));
});

function getDialogActionsUtilityClass(slot) {
  return generateUtilityClass('MuiDialogActions', slot);
}
generateUtilityClasses('MuiDialogActions', ['root', 'spacing']);

const _excluded$8 = ["className", "disableSpacing"];
const useUtilityClasses$3 = (ownerState) => {
  const {
    classes,
    disableSpacing
  } = ownerState;
  const slots = {
    root: ["root", !disableSpacing && "spacing"]
  };
  return composeClasses(slots, getDialogActionsUtilityClass, classes);
};
const DialogActionsRoot = styled$1("div", {
  name: "MuiDialogActions",
  slot: "Root",
  overridesResolver: (props, styles) => {
    const {
      ownerState
    } = props;
    return [styles.root, !ownerState.disableSpacing && styles.spacing];
  }
})(({
  ownerState
}) => _extends$1({
  display: "flex",
  alignItems: "center",
  padding: 8,
  justifyContent: "flex-end",
  flex: "0 0 auto"
}, !ownerState.disableSpacing && {
  "& > :not(style) ~ :not(style)": {
    marginLeft: 8
  }
}));
const DialogActions = /* @__PURE__ */ reactExports.forwardRef(function DialogActions2(inProps, ref) {
  const props = useDefaultProps({
    props: inProps,
    name: "MuiDialogActions"
  });
  const {
    className,
    disableSpacing = false
  } = props, other = _objectWithoutPropertiesLoose(props, _excluded$8);
  const ownerState = _extends$1({}, props, {
    disableSpacing
  });
  const classes = useUtilityClasses$3(ownerState);
  return /* @__PURE__ */ jsxRuntimeExports.jsx(DialogActionsRoot, _extends$1({
    className: clsx$1(classes.root, className),
    ownerState,
    ref
  }, other));
});

function getDialogContentUtilityClass(slot) {
  return generateUtilityClass('MuiDialogContent', slot);
}
generateUtilityClasses('MuiDialogContent', ['root', 'dividers']);

function getDialogTitleUtilityClass(slot) {
  return generateUtilityClass('MuiDialogTitle', slot);
}
const dialogTitleClasses = generateUtilityClasses('MuiDialogTitle', ['root']);

const _excluded$7 = ["className", "dividers"];
const useUtilityClasses$2 = (ownerState) => {
  const {
    classes,
    dividers
  } = ownerState;
  const slots = {
    root: ["root", dividers && "dividers"]
  };
  return composeClasses(slots, getDialogContentUtilityClass, classes);
};
const DialogContentRoot = styled$1("div", {
  name: "MuiDialogContent",
  slot: "Root",
  overridesResolver: (props, styles) => {
    const {
      ownerState
    } = props;
    return [styles.root, ownerState.dividers && styles.dividers];
  }
})(({
  theme,
  ownerState
}) => _extends$1({
  flex: "1 1 auto",
  // Add iOS momentum scrolling for iOS < 13.0
  WebkitOverflowScrolling: "touch",
  overflowY: "auto",
  padding: "20px 24px"
}, ownerState.dividers ? {
  padding: "16px 24px",
  borderTop: `1px solid ${(theme.vars || theme).palette.divider}`,
  borderBottom: `1px solid ${(theme.vars || theme).palette.divider}`
} : {
  [`.${dialogTitleClasses.root} + &`]: {
    paddingTop: 0
  }
}));
const DialogContent = /* @__PURE__ */ reactExports.forwardRef(function DialogContent2(inProps, ref) {
  const props = useDefaultProps({
    props: inProps,
    name: "MuiDialogContent"
  });
  const {
    className,
    dividers = false
  } = props, other = _objectWithoutPropertiesLoose(props, _excluded$7);
  const ownerState = _extends$1({}, props, {
    dividers
  });
  const classes = useUtilityClasses$2(ownerState);
  return /* @__PURE__ */ jsxRuntimeExports.jsx(DialogContentRoot, _extends$1({
    className: clsx$1(classes.root, className),
    ownerState,
    ref
  }, other));
});

const _excluded$6 = ["className", "id"];
const useUtilityClasses$1 = (ownerState) => {
  const {
    classes
  } = ownerState;
  const slots = {
    root: ["root"]
  };
  return composeClasses(slots, getDialogTitleUtilityClass, classes);
};
const DialogTitleRoot = styled$1(Typography, {
  name: "MuiDialogTitle",
  slot: "Root",
  overridesResolver: (props, styles) => styles.root
})({
  padding: "16px 24px",
  flex: "0 0 auto"
});
const DialogTitle = /* @__PURE__ */ reactExports.forwardRef(function DialogTitle2(inProps, ref) {
  const props = useDefaultProps({
    props: inProps,
    name: "MuiDialogTitle"
  });
  const {
    className,
    id: idProp
  } = props, other = _objectWithoutPropertiesLoose(props, _excluded$6);
  const ownerState = props;
  const classes = useUtilityClasses$1(ownerState);
  const {
    titleId = idProp
  } = reactExports.useContext(DialogContext);
  return /* @__PURE__ */ jsxRuntimeExports.jsx(DialogTitleRoot, _extends$1({
    component: "h2",
    className: clsx$1(classes.root, className),
    ownerState,
    ref,
    variant: "h6",
    id: idProp != null ? idProp : titleId
  }, other));
});

const _excluded$5 = ["children", "className", "disableTypography", "inset", "primary", "primaryTypographyProps", "secondary", "secondaryTypographyProps"];
const useUtilityClasses = (ownerState) => {
  const {
    classes,
    inset,
    primary,
    secondary,
    dense
  } = ownerState;
  const slots = {
    root: ["root", inset && "inset", dense && "dense", primary && secondary && "multiline"],
    primary: ["primary"],
    secondary: ["secondary"]
  };
  return composeClasses(slots, getListItemTextUtilityClass, classes);
};
const ListItemTextRoot = styled$1("div", {
  name: "MuiListItemText",
  slot: "Root",
  overridesResolver: (props, styles) => {
    const {
      ownerState
    } = props;
    return [{
      [`& .${listItemTextClasses.primary}`]: styles.primary
    }, {
      [`& .${listItemTextClasses.secondary}`]: styles.secondary
    }, styles.root, ownerState.inset && styles.inset, ownerState.primary && ownerState.secondary && styles.multiline, ownerState.dense && styles.dense];
  }
})(({
  ownerState
}) => _extends$1({
  flex: "1 1 auto",
  minWidth: 0,
  marginTop: 4,
  marginBottom: 4
}, ownerState.primary && ownerState.secondary && {
  marginTop: 6,
  marginBottom: 6
}, ownerState.inset && {
  paddingLeft: 56
}));
const ListItemText = /* @__PURE__ */ reactExports.forwardRef(function ListItemText2(inProps, ref) {
  const props = useDefaultProps({
    props: inProps,
    name: "MuiListItemText"
  });
  const {
    children,
    className,
    disableTypography = false,
    inset = false,
    primary: primaryProp,
    primaryTypographyProps,
    secondary: secondaryProp,
    secondaryTypographyProps
  } = props, other = _objectWithoutPropertiesLoose(props, _excluded$5);
  const {
    dense
  } = reactExports.useContext(ListContext);
  let primary = primaryProp != null ? primaryProp : children;
  let secondary = secondaryProp;
  const ownerState = _extends$1({}, props, {
    disableTypography,
    inset,
    primary: !!primary,
    secondary: !!secondary,
    dense
  });
  const classes = useUtilityClasses(ownerState);
  if (primary != null && primary.type !== Typography && !disableTypography) {
    primary = /* @__PURE__ */ jsxRuntimeExports.jsx(Typography, _extends$1({
      variant: dense ? "body2" : "body1",
      className: classes.primary,
      component: primaryTypographyProps != null && primaryTypographyProps.variant ? void 0 : "span",
      display: "block"
    }, primaryTypographyProps, {
      children: primary
    }));
  }
  if (secondary != null && secondary.type !== Typography && !disableTypography) {
    secondary = /* @__PURE__ */ jsxRuntimeExports.jsx(Typography, _extends$1({
      variant: "body2",
      className: classes.secondary,
      color: "text.secondary",
      display: "block"
    }, secondaryTypographyProps, {
      children: secondary
    }));
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(ListItemTextRoot, _extends$1({
    className: clsx$1(classes.root, className),
    ownerState,
    ref
  }, other, {
    children: [primary, secondary]
  }));
});

var Fragment = jsxRuntimeExports.Fragment;
var jsx = function jsx(type, props, key) {
  if (!hasOwn.call(props, 'css')) {
    return jsxRuntimeExports.jsx(type, props, key);
  }

  return jsxRuntimeExports.jsx(Emotion$1, createEmotionProps(type, props), key);
};
var jsxs = function jsxs(type, props, key) {
  if (!hasOwn.call(props, 'css')) {
    return jsxRuntimeExports.jsxs(type, props, key);
  }

  return jsxRuntimeExports.jsxs(Emotion$1, createEmotionProps(type, props), key);
};

/**
 * A specialized version of `_.map` for arrays without support for iteratee
 * shorthands.
 *
 * @private
 * @param {Array} [array] The array to iterate over.
 * @param {Function} iteratee The function invoked per iteration.
 * @returns {Array} Returns the new mapped array.
 */

var _arrayMap;
var hasRequired_arrayMap;

function require_arrayMap () {
	if (hasRequired_arrayMap) return _arrayMap;
	hasRequired_arrayMap = 1;
	function arrayMap(array, iteratee) {
	  var index = -1,
	      length = array == null ? 0 : array.length,
	      result = Array(length);

	  while (++index < length) {
	    result[index] = iteratee(array[index], index, array);
	  }
	  return result;
	}

	_arrayMap = arrayMap;
	return _arrayMap;
}

/**
 * Removes all key-value entries from the list cache.
 *
 * @private
 * @name clear
 * @memberOf ListCache
 */

var _listCacheClear;
var hasRequired_listCacheClear;

function require_listCacheClear () {
	if (hasRequired_listCacheClear) return _listCacheClear;
	hasRequired_listCacheClear = 1;
	function listCacheClear() {
	  this.__data__ = [];
	  this.size = 0;
	}

	_listCacheClear = listCacheClear;
	return _listCacheClear;
}

/**
 * Performs a
 * [`SameValueZero`](http://ecma-international.org/ecma-262/7.0/#sec-samevaluezero)
 * comparison between two values to determine if they are equivalent.
 *
 * @static
 * @memberOf _
 * @since 4.0.0
 * @category Lang
 * @param {*} value The value to compare.
 * @param {*} other The other value to compare.
 * @returns {boolean} Returns `true` if the values are equivalent, else `false`.
 * @example
 *
 * var object = { 'a': 1 };
 * var other = { 'a': 1 };
 *
 * _.eq(object, object);
 * // => true
 *
 * _.eq(object, other);
 * // => false
 *
 * _.eq('a', 'a');
 * // => true
 *
 * _.eq('a', Object('a'));
 * // => false
 *
 * _.eq(NaN, NaN);
 * // => true
 */

var eq_1;
var hasRequiredEq;

function requireEq () {
	if (hasRequiredEq) return eq_1;
	hasRequiredEq = 1;
	function eq(value, other) {
	  return value === other || (value !== value && other !== other);
	}

	eq_1 = eq;
	return eq_1;
}

var _assocIndexOf;
var hasRequired_assocIndexOf;

function require_assocIndexOf () {
	if (hasRequired_assocIndexOf) return _assocIndexOf;
	hasRequired_assocIndexOf = 1;
	var eq = requireEq();

	/**
	 * Gets the index at which the `key` is found in `array` of key-value pairs.
	 *
	 * @private
	 * @param {Array} array The array to inspect.
	 * @param {*} key The key to search for.
	 * @returns {number} Returns the index of the matched value, else `-1`.
	 */
	function assocIndexOf(array, key) {
	  var length = array.length;
	  while (length--) {
	    if (eq(array[length][0], key)) {
	      return length;
	    }
	  }
	  return -1;
	}

	_assocIndexOf = assocIndexOf;
	return _assocIndexOf;
}

var _listCacheDelete;
var hasRequired_listCacheDelete;

function require_listCacheDelete () {
	if (hasRequired_listCacheDelete) return _listCacheDelete;
	hasRequired_listCacheDelete = 1;
	var assocIndexOf = require_assocIndexOf();

	/** Used for built-in method references. */
	var arrayProto = Array.prototype;

	/** Built-in value references. */
	var splice = arrayProto.splice;

	/**
	 * Removes `key` and its value from the list cache.
	 *
	 * @private
	 * @name delete
	 * @memberOf ListCache
	 * @param {string} key The key of the value to remove.
	 * @returns {boolean} Returns `true` if the entry was removed, else `false`.
	 */
	function listCacheDelete(key) {
	  var data = this.__data__,
	      index = assocIndexOf(data, key);

	  if (index < 0) {
	    return false;
	  }
	  var lastIndex = data.length - 1;
	  if (index == lastIndex) {
	    data.pop();
	  } else {
	    splice.call(data, index, 1);
	  }
	  --this.size;
	  return true;
	}

	_listCacheDelete = listCacheDelete;
	return _listCacheDelete;
}

var _listCacheGet;
var hasRequired_listCacheGet;

function require_listCacheGet () {
	if (hasRequired_listCacheGet) return _listCacheGet;
	hasRequired_listCacheGet = 1;
	var assocIndexOf = require_assocIndexOf();

	/**
	 * Gets the list cache value for `key`.
	 *
	 * @private
	 * @name get
	 * @memberOf ListCache
	 * @param {string} key The key of the value to get.
	 * @returns {*} Returns the entry value.
	 */
	function listCacheGet(key) {
	  var data = this.__data__,
	      index = assocIndexOf(data, key);

	  return index < 0 ? undefined : data[index][1];
	}

	_listCacheGet = listCacheGet;
	return _listCacheGet;
}

var _listCacheHas;
var hasRequired_listCacheHas;

function require_listCacheHas () {
	if (hasRequired_listCacheHas) return _listCacheHas;
	hasRequired_listCacheHas = 1;
	var assocIndexOf = require_assocIndexOf();

	/**
	 * Checks if a list cache value for `key` exists.
	 *
	 * @private
	 * @name has
	 * @memberOf ListCache
	 * @param {string} key The key of the entry to check.
	 * @returns {boolean} Returns `true` if an entry for `key` exists, else `false`.
	 */
	function listCacheHas(key) {
	  return assocIndexOf(this.__data__, key) > -1;
	}

	_listCacheHas = listCacheHas;
	return _listCacheHas;
}

var _listCacheSet;
var hasRequired_listCacheSet;

function require_listCacheSet () {
	if (hasRequired_listCacheSet) return _listCacheSet;
	hasRequired_listCacheSet = 1;
	var assocIndexOf = require_assocIndexOf();

	/**
	 * Sets the list cache `key` to `value`.
	 *
	 * @private
	 * @name set
	 * @memberOf ListCache
	 * @param {string} key The key of the value to set.
	 * @param {*} value The value to set.
	 * @returns {Object} Returns the list cache instance.
	 */
	function listCacheSet(key, value) {
	  var data = this.__data__,
	      index = assocIndexOf(data, key);

	  if (index < 0) {
	    ++this.size;
	    data.push([key, value]);
	  } else {
	    data[index][1] = value;
	  }
	  return this;
	}

	_listCacheSet = listCacheSet;
	return _listCacheSet;
}

var _ListCache;
var hasRequired_ListCache;

function require_ListCache () {
	if (hasRequired_ListCache) return _ListCache;
	hasRequired_ListCache = 1;
	var listCacheClear = require_listCacheClear(),
	    listCacheDelete = require_listCacheDelete(),
	    listCacheGet = require_listCacheGet(),
	    listCacheHas = require_listCacheHas(),
	    listCacheSet = require_listCacheSet();

	/**
	 * Creates an list cache object.
	 *
	 * @private
	 * @constructor
	 * @param {Array} [entries] The key-value pairs to cache.
	 */
	function ListCache(entries) {
	  var index = -1,
	      length = entries == null ? 0 : entries.length;

	  this.clear();
	  while (++index < length) {
	    var entry = entries[index];
	    this.set(entry[0], entry[1]);
	  }
	}

	// Add methods to `ListCache`.
	ListCache.prototype.clear = listCacheClear;
	ListCache.prototype['delete'] = listCacheDelete;
	ListCache.prototype.get = listCacheGet;
	ListCache.prototype.has = listCacheHas;
	ListCache.prototype.set = listCacheSet;

	_ListCache = ListCache;
	return _ListCache;
}

var _stackClear;
var hasRequired_stackClear;

function require_stackClear () {
	if (hasRequired_stackClear) return _stackClear;
	hasRequired_stackClear = 1;
	var ListCache = require_ListCache();

	/**
	 * Removes all key-value entries from the stack.
	 *
	 * @private
	 * @name clear
	 * @memberOf Stack
	 */
	function stackClear() {
	  this.__data__ = new ListCache;
	  this.size = 0;
	}

	_stackClear = stackClear;
	return _stackClear;
}

/**
 * Removes `key` and its value from the stack.
 *
 * @private
 * @name delete
 * @memberOf Stack
 * @param {string} key The key of the value to remove.
 * @returns {boolean} Returns `true` if the entry was removed, else `false`.
 */

var _stackDelete;
var hasRequired_stackDelete;

function require_stackDelete () {
	if (hasRequired_stackDelete) return _stackDelete;
	hasRequired_stackDelete = 1;
	function stackDelete(key) {
	  var data = this.__data__,
	      result = data['delete'](key);

	  this.size = data.size;
	  return result;
	}

	_stackDelete = stackDelete;
	return _stackDelete;
}

/**
 * Gets the stack value for `key`.
 *
 * @private
 * @name get
 * @memberOf Stack
 * @param {string} key The key of the value to get.
 * @returns {*} Returns the entry value.
 */

var _stackGet;
var hasRequired_stackGet;

function require_stackGet () {
	if (hasRequired_stackGet) return _stackGet;
	hasRequired_stackGet = 1;
	function stackGet(key) {
	  return this.__data__.get(key);
	}

	_stackGet = stackGet;
	return _stackGet;
}

/**
 * Checks if a stack value for `key` exists.
 *
 * @private
 * @name has
 * @memberOf Stack
 * @param {string} key The key of the entry to check.
 * @returns {boolean} Returns `true` if an entry for `key` exists, else `false`.
 */

var _stackHas;
var hasRequired_stackHas;

function require_stackHas () {
	if (hasRequired_stackHas) return _stackHas;
	hasRequired_stackHas = 1;
	function stackHas(key) {
	  return this.__data__.has(key);
	}

	_stackHas = stackHas;
	return _stackHas;
}

var _freeGlobal;
var hasRequired_freeGlobal;

function require_freeGlobal () {
	if (hasRequired_freeGlobal) return _freeGlobal;
	hasRequired_freeGlobal = 1;
	var freeGlobal = typeof globalThis == "object" && globalThis && globalThis.Object === Object && globalThis;
	_freeGlobal = freeGlobal;
	return _freeGlobal;
}

var _root;
var hasRequired_root;

function require_root () {
	if (hasRequired_root) return _root;
	hasRequired_root = 1;
	var freeGlobal = require_freeGlobal();
	var freeSelf = typeof self == "object" && self && self.Object === Object && self;
	var root = freeGlobal || freeSelf || Function("return this")();
	_root = root;
	return _root;
}

var _Symbol;
var hasRequired_Symbol;

function require_Symbol () {
	if (hasRequired_Symbol) return _Symbol;
	hasRequired_Symbol = 1;
	var root = require_root();

	/** Built-in value references. */
	var Symbol = root.Symbol;

	_Symbol = Symbol;
	return _Symbol;
}

var _getRawTag;
var hasRequired_getRawTag;

function require_getRawTag () {
	if (hasRequired_getRawTag) return _getRawTag;
	hasRequired_getRawTag = 1;
	var Symbol = require_Symbol();

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/**
	 * Used to resolve the
	 * [`toStringTag`](http://ecma-international.org/ecma-262/7.0/#sec-object.prototype.tostring)
	 * of values.
	 */
	var nativeObjectToString = objectProto.toString;

	/** Built-in value references. */
	var symToStringTag = Symbol ? Symbol.toStringTag : undefined;

	/**
	 * A specialized version of `baseGetTag` which ignores `Symbol.toStringTag` values.
	 *
	 * @private
	 * @param {*} value The value to query.
	 * @returns {string} Returns the raw `toStringTag`.
	 */
	function getRawTag(value) {
	  var isOwn = hasOwnProperty.call(value, symToStringTag),
	      tag = value[symToStringTag];

	  try {
	    value[symToStringTag] = undefined;
	    var unmasked = true;
	  } catch (e) {}

	  var result = nativeObjectToString.call(value);
	  if (unmasked) {
	    if (isOwn) {
	      value[symToStringTag] = tag;
	    } else {
	      delete value[symToStringTag];
	    }
	  }
	  return result;
	}

	_getRawTag = getRawTag;
	return _getRawTag;
}

/** Used for built-in method references. */

var _objectToString;
var hasRequired_objectToString;

function require_objectToString () {
	if (hasRequired_objectToString) return _objectToString;
	hasRequired_objectToString = 1;
	var objectProto = Object.prototype;

	/**
	 * Used to resolve the
	 * [`toStringTag`](http://ecma-international.org/ecma-262/7.0/#sec-object.prototype.tostring)
	 * of values.
	 */
	var nativeObjectToString = objectProto.toString;

	/**
	 * Converts `value` to a string using `Object.prototype.toString`.
	 *
	 * @private
	 * @param {*} value The value to convert.
	 * @returns {string} Returns the converted string.
	 */
	function objectToString(value) {
	  return nativeObjectToString.call(value);
	}

	_objectToString = objectToString;
	return _objectToString;
}

var _baseGetTag;
var hasRequired_baseGetTag;

function require_baseGetTag () {
	if (hasRequired_baseGetTag) return _baseGetTag;
	hasRequired_baseGetTag = 1;
	var Symbol = require_Symbol(),
	    getRawTag = require_getRawTag(),
	    objectToString = require_objectToString();

	/** `Object#toString` result references. */
	var nullTag = '[object Null]',
	    undefinedTag = '[object Undefined]';

	/** Built-in value references. */
	var symToStringTag = Symbol ? Symbol.toStringTag : undefined;

	/**
	 * The base implementation of `getTag` without fallbacks for buggy environments.
	 *
	 * @private
	 * @param {*} value The value to query.
	 * @returns {string} Returns the `toStringTag`.
	 */
	function baseGetTag(value) {
	  if (value == null) {
	    return value === undefined ? undefinedTag : nullTag;
	  }
	  return (symToStringTag && symToStringTag in Object(value))
	    ? getRawTag(value)
	    : objectToString(value);
	}

	_baseGetTag = baseGetTag;
	return _baseGetTag;
}

/**
 * Checks if `value` is the
 * [language type](http://www.ecma-international.org/ecma-262/7.0/#sec-ecmascript-language-types)
 * of `Object`. (e.g. arrays, functions, objects, regexes, `new Number(0)`, and `new String('')`)
 *
 * @static
 * @memberOf _
 * @since 0.1.0
 * @category Lang
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is an object, else `false`.
 * @example
 *
 * _.isObject({});
 * // => true
 *
 * _.isObject([1, 2, 3]);
 * // => true
 *
 * _.isObject(_.noop);
 * // => true
 *
 * _.isObject(null);
 * // => false
 */

var isObject_1;
var hasRequiredIsObject;

function requireIsObject () {
	if (hasRequiredIsObject) return isObject_1;
	hasRequiredIsObject = 1;
	function isObject(value) {
	  var type = typeof value;
	  return value != null && (type == 'object' || type == 'function');
	}

	isObject_1 = isObject;
	return isObject_1;
}

var isFunction_1;
var hasRequiredIsFunction;

function requireIsFunction () {
	if (hasRequiredIsFunction) return isFunction_1;
	hasRequiredIsFunction = 1;
	var baseGetTag = require_baseGetTag(),
	    isObject = requireIsObject();

	/** `Object#toString` result references. */
	var asyncTag = '[object AsyncFunction]',
	    funcTag = '[object Function]',
	    genTag = '[object GeneratorFunction]',
	    proxyTag = '[object Proxy]';

	/**
	 * Checks if `value` is classified as a `Function` object.
	 *
	 * @static
	 * @memberOf _
	 * @since 0.1.0
	 * @category Lang
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a function, else `false`.
	 * @example
	 *
	 * _.isFunction(_);
	 * // => true
	 *
	 * _.isFunction(/abc/);
	 * // => false
	 */
	function isFunction(value) {
	  if (!isObject(value)) {
	    return false;
	  }
	  // The use of `Object#toString` avoids issues with the `typeof` operator
	  // in Safari 9 which returns 'object' for typed arrays and other constructors.
	  var tag = baseGetTag(value);
	  return tag == funcTag || tag == genTag || tag == asyncTag || tag == proxyTag;
	}

	isFunction_1 = isFunction;
	return isFunction_1;
}

var _coreJsData;
var hasRequired_coreJsData;

function require_coreJsData () {
	if (hasRequired_coreJsData) return _coreJsData;
	hasRequired_coreJsData = 1;
	var root = require_root();

	/** Used to detect overreaching core-js shims. */
	var coreJsData = root['__core-js_shared__'];

	_coreJsData = coreJsData;
	return _coreJsData;
}

var _isMasked;
var hasRequired_isMasked;

function require_isMasked () {
	if (hasRequired_isMasked) return _isMasked;
	hasRequired_isMasked = 1;
	var coreJsData = require_coreJsData();

	/** Used to detect methods masquerading as native. */
	var maskSrcKey = (function() {
	  var uid = /[^.]+$/.exec(coreJsData && coreJsData.keys && coreJsData.keys.IE_PROTO || '');
	  return uid ? ('Symbol(src)_1.' + uid) : '';
	}());

	/**
	 * Checks if `func` has its source masked.
	 *
	 * @private
	 * @param {Function} func The function to check.
	 * @returns {boolean} Returns `true` if `func` is masked, else `false`.
	 */
	function isMasked(func) {
	  return !!maskSrcKey && (maskSrcKey in func);
	}

	_isMasked = isMasked;
	return _isMasked;
}

/** Used for built-in method references. */

var _toSource;
var hasRequired_toSource;

function require_toSource () {
	if (hasRequired_toSource) return _toSource;
	hasRequired_toSource = 1;
	var funcProto = Function.prototype;

	/** Used to resolve the decompiled source of functions. */
	var funcToString = funcProto.toString;

	/**
	 * Converts `func` to its source code.
	 *
	 * @private
	 * @param {Function} func The function to convert.
	 * @returns {string} Returns the source code.
	 */
	function toSource(func) {
	  if (func != null) {
	    try {
	      return funcToString.call(func);
	    } catch (e) {}
	    try {
	      return (func + '');
	    } catch (e) {}
	  }
	  return '';
	}

	_toSource = toSource;
	return _toSource;
}

var _baseIsNative;
var hasRequired_baseIsNative;

function require_baseIsNative () {
	if (hasRequired_baseIsNative) return _baseIsNative;
	hasRequired_baseIsNative = 1;
	var isFunction = requireIsFunction(),
	    isMasked = require_isMasked(),
	    isObject = requireIsObject(),
	    toSource = require_toSource();

	/**
	 * Used to match `RegExp`
	 * [syntax characters](http://ecma-international.org/ecma-262/7.0/#sec-patterns).
	 */
	var reRegExpChar = /[\\^$.*+?()[\]{}|]/g;

	/** Used to detect host constructors (Safari). */
	var reIsHostCtor = /^\[object .+?Constructor\]$/;

	/** Used for built-in method references. */
	var funcProto = Function.prototype,
	    objectProto = Object.prototype;

	/** Used to resolve the decompiled source of functions. */
	var funcToString = funcProto.toString;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/** Used to detect if a method is native. */
	var reIsNative = RegExp('^' +
	  funcToString.call(hasOwnProperty).replace(reRegExpChar, '\\$&')
	  .replace(/hasOwnProperty|(function).*?(?=\\\()| for .+?(?=\\\])/g, '$1.*?') + '$'
	);

	/**
	 * The base implementation of `_.isNative` without bad shim checks.
	 *
	 * @private
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a native function,
	 *  else `false`.
	 */
	function baseIsNative(value) {
	  if (!isObject(value) || isMasked(value)) {
	    return false;
	  }
	  var pattern = isFunction(value) ? reIsNative : reIsHostCtor;
	  return pattern.test(toSource(value));
	}

	_baseIsNative = baseIsNative;
	return _baseIsNative;
}

/**
 * Gets the value at `key` of `object`.
 *
 * @private
 * @param {Object} [object] The object to query.
 * @param {string} key The key of the property to get.
 * @returns {*} Returns the property value.
 */

var _getValue;
var hasRequired_getValue;

function require_getValue () {
	if (hasRequired_getValue) return _getValue;
	hasRequired_getValue = 1;
	function getValue(object, key) {
	  return object == null ? undefined : object[key];
	}

	_getValue = getValue;
	return _getValue;
}

var _getNative;
var hasRequired_getNative;

function require_getNative () {
	if (hasRequired_getNative) return _getNative;
	hasRequired_getNative = 1;
	var baseIsNative = require_baseIsNative(),
	    getValue = require_getValue();

	/**
	 * Gets the native function at `key` of `object`.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @param {string} key The key of the method to get.
	 * @returns {*} Returns the function if it's native, else `undefined`.
	 */
	function getNative(object, key) {
	  var value = getValue(object, key);
	  return baseIsNative(value) ? value : undefined;
	}

	_getNative = getNative;
	return _getNative;
}

var _Map;
var hasRequired_Map;

function require_Map () {
	if (hasRequired_Map) return _Map;
	hasRequired_Map = 1;
	var getNative = require_getNative(),
	    root = require_root();

	/* Built-in method references that are verified to be native. */
	var Map = getNative(root, 'Map');

	_Map = Map;
	return _Map;
}

var _nativeCreate;
var hasRequired_nativeCreate;

function require_nativeCreate () {
	if (hasRequired_nativeCreate) return _nativeCreate;
	hasRequired_nativeCreate = 1;
	var getNative = require_getNative();

	/* Built-in method references that are verified to be native. */
	var nativeCreate = getNative(Object, 'create');

	_nativeCreate = nativeCreate;
	return _nativeCreate;
}

var _hashClear;
var hasRequired_hashClear;

function require_hashClear () {
	if (hasRequired_hashClear) return _hashClear;
	hasRequired_hashClear = 1;
	var nativeCreate = require_nativeCreate();

	/**
	 * Removes all key-value entries from the hash.
	 *
	 * @private
	 * @name clear
	 * @memberOf Hash
	 */
	function hashClear() {
	  this.__data__ = nativeCreate ? nativeCreate(null) : {};
	  this.size = 0;
	}

	_hashClear = hashClear;
	return _hashClear;
}

/**
 * Removes `key` and its value from the hash.
 *
 * @private
 * @name delete
 * @memberOf Hash
 * @param {Object} hash The hash to modify.
 * @param {string} key The key of the value to remove.
 * @returns {boolean} Returns `true` if the entry was removed, else `false`.
 */

var _hashDelete;
var hasRequired_hashDelete;

function require_hashDelete () {
	if (hasRequired_hashDelete) return _hashDelete;
	hasRequired_hashDelete = 1;
	function hashDelete(key) {
	  var result = this.has(key) && delete this.__data__[key];
	  this.size -= result ? 1 : 0;
	  return result;
	}

	_hashDelete = hashDelete;
	return _hashDelete;
}

var _hashGet;
var hasRequired_hashGet;

function require_hashGet () {
	if (hasRequired_hashGet) return _hashGet;
	hasRequired_hashGet = 1;
	var nativeCreate = require_nativeCreate();

	/** Used to stand-in for `undefined` hash values. */
	var HASH_UNDEFINED = '__lodash_hash_undefined__';

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/**
	 * Gets the hash value for `key`.
	 *
	 * @private
	 * @name get
	 * @memberOf Hash
	 * @param {string} key The key of the value to get.
	 * @returns {*} Returns the entry value.
	 */
	function hashGet(key) {
	  var data = this.__data__;
	  if (nativeCreate) {
	    var result = data[key];
	    return result === HASH_UNDEFINED ? undefined : result;
	  }
	  return hasOwnProperty.call(data, key) ? data[key] : undefined;
	}

	_hashGet = hashGet;
	return _hashGet;
}

var _hashHas;
var hasRequired_hashHas;

function require_hashHas () {
	if (hasRequired_hashHas) return _hashHas;
	hasRequired_hashHas = 1;
	var nativeCreate = require_nativeCreate();

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/**
	 * Checks if a hash value for `key` exists.
	 *
	 * @private
	 * @name has
	 * @memberOf Hash
	 * @param {string} key The key of the entry to check.
	 * @returns {boolean} Returns `true` if an entry for `key` exists, else `false`.
	 */
	function hashHas(key) {
	  var data = this.__data__;
	  return nativeCreate ? (data[key] !== undefined) : hasOwnProperty.call(data, key);
	}

	_hashHas = hashHas;
	return _hashHas;
}

var _hashSet;
var hasRequired_hashSet;

function require_hashSet () {
	if (hasRequired_hashSet) return _hashSet;
	hasRequired_hashSet = 1;
	var nativeCreate = require_nativeCreate();

	/** Used to stand-in for `undefined` hash values. */
	var HASH_UNDEFINED = '__lodash_hash_undefined__';

	/**
	 * Sets the hash `key` to `value`.
	 *
	 * @private
	 * @name set
	 * @memberOf Hash
	 * @param {string} key The key of the value to set.
	 * @param {*} value The value to set.
	 * @returns {Object} Returns the hash instance.
	 */
	function hashSet(key, value) {
	  var data = this.__data__;
	  this.size += this.has(key) ? 0 : 1;
	  data[key] = (nativeCreate && value === undefined) ? HASH_UNDEFINED : value;
	  return this;
	}

	_hashSet = hashSet;
	return _hashSet;
}

var _Hash;
var hasRequired_Hash;

function require_Hash () {
	if (hasRequired_Hash) return _Hash;
	hasRequired_Hash = 1;
	var hashClear = require_hashClear(),
	    hashDelete = require_hashDelete(),
	    hashGet = require_hashGet(),
	    hashHas = require_hashHas(),
	    hashSet = require_hashSet();

	/**
	 * Creates a hash object.
	 *
	 * @private
	 * @constructor
	 * @param {Array} [entries] The key-value pairs to cache.
	 */
	function Hash(entries) {
	  var index = -1,
	      length = entries == null ? 0 : entries.length;

	  this.clear();
	  while (++index < length) {
	    var entry = entries[index];
	    this.set(entry[0], entry[1]);
	  }
	}

	// Add methods to `Hash`.
	Hash.prototype.clear = hashClear;
	Hash.prototype['delete'] = hashDelete;
	Hash.prototype.get = hashGet;
	Hash.prototype.has = hashHas;
	Hash.prototype.set = hashSet;

	_Hash = Hash;
	return _Hash;
}

var _mapCacheClear;
var hasRequired_mapCacheClear;

function require_mapCacheClear () {
	if (hasRequired_mapCacheClear) return _mapCacheClear;
	hasRequired_mapCacheClear = 1;
	var Hash = require_Hash(),
	    ListCache = require_ListCache(),
	    Map = require_Map();

	/**
	 * Removes all key-value entries from the map.
	 *
	 * @private
	 * @name clear
	 * @memberOf MapCache
	 */
	function mapCacheClear() {
	  this.size = 0;
	  this.__data__ = {
	    'hash': new Hash,
	    'map': new (Map || ListCache),
	    'string': new Hash
	  };
	}

	_mapCacheClear = mapCacheClear;
	return _mapCacheClear;
}

/**
 * Checks if `value` is suitable for use as unique object key.
 *
 * @private
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is suitable, else `false`.
 */

var _isKeyable;
var hasRequired_isKeyable;

function require_isKeyable () {
	if (hasRequired_isKeyable) return _isKeyable;
	hasRequired_isKeyable = 1;
	function isKeyable(value) {
	  var type = typeof value;
	  return (type == 'string' || type == 'number' || type == 'symbol' || type == 'boolean')
	    ? (value !== '__proto__')
	    : (value === null);
	}

	_isKeyable = isKeyable;
	return _isKeyable;
}

var _getMapData;
var hasRequired_getMapData;

function require_getMapData () {
	if (hasRequired_getMapData) return _getMapData;
	hasRequired_getMapData = 1;
	var isKeyable = require_isKeyable();

	/**
	 * Gets the data for `map`.
	 *
	 * @private
	 * @param {Object} map The map to query.
	 * @param {string} key The reference key.
	 * @returns {*} Returns the map data.
	 */
	function getMapData(map, key) {
	  var data = map.__data__;
	  return isKeyable(key)
	    ? data[typeof key == 'string' ? 'string' : 'hash']
	    : data.map;
	}

	_getMapData = getMapData;
	return _getMapData;
}

var _mapCacheDelete;
var hasRequired_mapCacheDelete;

function require_mapCacheDelete () {
	if (hasRequired_mapCacheDelete) return _mapCacheDelete;
	hasRequired_mapCacheDelete = 1;
	var getMapData = require_getMapData();

	/**
	 * Removes `key` and its value from the map.
	 *
	 * @private
	 * @name delete
	 * @memberOf MapCache
	 * @param {string} key The key of the value to remove.
	 * @returns {boolean} Returns `true` if the entry was removed, else `false`.
	 */
	function mapCacheDelete(key) {
	  var result = getMapData(this, key)['delete'](key);
	  this.size -= result ? 1 : 0;
	  return result;
	}

	_mapCacheDelete = mapCacheDelete;
	return _mapCacheDelete;
}

var _mapCacheGet;
var hasRequired_mapCacheGet;

function require_mapCacheGet () {
	if (hasRequired_mapCacheGet) return _mapCacheGet;
	hasRequired_mapCacheGet = 1;
	var getMapData = require_getMapData();

	/**
	 * Gets the map value for `key`.
	 *
	 * @private
	 * @name get
	 * @memberOf MapCache
	 * @param {string} key The key of the value to get.
	 * @returns {*} Returns the entry value.
	 */
	function mapCacheGet(key) {
	  return getMapData(this, key).get(key);
	}

	_mapCacheGet = mapCacheGet;
	return _mapCacheGet;
}

var _mapCacheHas;
var hasRequired_mapCacheHas;

function require_mapCacheHas () {
	if (hasRequired_mapCacheHas) return _mapCacheHas;
	hasRequired_mapCacheHas = 1;
	var getMapData = require_getMapData();

	/**
	 * Checks if a map value for `key` exists.
	 *
	 * @private
	 * @name has
	 * @memberOf MapCache
	 * @param {string} key The key of the entry to check.
	 * @returns {boolean} Returns `true` if an entry for `key` exists, else `false`.
	 */
	function mapCacheHas(key) {
	  return getMapData(this, key).has(key);
	}

	_mapCacheHas = mapCacheHas;
	return _mapCacheHas;
}

var _mapCacheSet;
var hasRequired_mapCacheSet;

function require_mapCacheSet () {
	if (hasRequired_mapCacheSet) return _mapCacheSet;
	hasRequired_mapCacheSet = 1;
	var getMapData = require_getMapData();

	/**
	 * Sets the map `key` to `value`.
	 *
	 * @private
	 * @name set
	 * @memberOf MapCache
	 * @param {string} key The key of the value to set.
	 * @param {*} value The value to set.
	 * @returns {Object} Returns the map cache instance.
	 */
	function mapCacheSet(key, value) {
	  var data = getMapData(this, key),
	      size = data.size;

	  data.set(key, value);
	  this.size += data.size == size ? 0 : 1;
	  return this;
	}

	_mapCacheSet = mapCacheSet;
	return _mapCacheSet;
}

var _MapCache;
var hasRequired_MapCache;

function require_MapCache () {
	if (hasRequired_MapCache) return _MapCache;
	hasRequired_MapCache = 1;
	var mapCacheClear = require_mapCacheClear(),
	    mapCacheDelete = require_mapCacheDelete(),
	    mapCacheGet = require_mapCacheGet(),
	    mapCacheHas = require_mapCacheHas(),
	    mapCacheSet = require_mapCacheSet();

	/**
	 * Creates a map cache object to store key-value pairs.
	 *
	 * @private
	 * @constructor
	 * @param {Array} [entries] The key-value pairs to cache.
	 */
	function MapCache(entries) {
	  var index = -1,
	      length = entries == null ? 0 : entries.length;

	  this.clear();
	  while (++index < length) {
	    var entry = entries[index];
	    this.set(entry[0], entry[1]);
	  }
	}

	// Add methods to `MapCache`.
	MapCache.prototype.clear = mapCacheClear;
	MapCache.prototype['delete'] = mapCacheDelete;
	MapCache.prototype.get = mapCacheGet;
	MapCache.prototype.has = mapCacheHas;
	MapCache.prototype.set = mapCacheSet;

	_MapCache = MapCache;
	return _MapCache;
}

var _stackSet;
var hasRequired_stackSet;

function require_stackSet () {
	if (hasRequired_stackSet) return _stackSet;
	hasRequired_stackSet = 1;
	var ListCache = require_ListCache(),
	    Map = require_Map(),
	    MapCache = require_MapCache();

	/** Used as the size to enable large array optimizations. */
	var LARGE_ARRAY_SIZE = 200;

	/**
	 * Sets the stack `key` to `value`.
	 *
	 * @private
	 * @name set
	 * @memberOf Stack
	 * @param {string} key The key of the value to set.
	 * @param {*} value The value to set.
	 * @returns {Object} Returns the stack cache instance.
	 */
	function stackSet(key, value) {
	  var data = this.__data__;
	  if (data instanceof ListCache) {
	    var pairs = data.__data__;
	    if (!Map || (pairs.length < LARGE_ARRAY_SIZE - 1)) {
	      pairs.push([key, value]);
	      this.size = ++data.size;
	      return this;
	    }
	    data = this.__data__ = new MapCache(pairs);
	  }
	  data.set(key, value);
	  this.size = data.size;
	  return this;
	}

	_stackSet = stackSet;
	return _stackSet;
}

var _Stack;
var hasRequired_Stack;

function require_Stack () {
	if (hasRequired_Stack) return _Stack;
	hasRequired_Stack = 1;
	var ListCache = require_ListCache(),
	    stackClear = require_stackClear(),
	    stackDelete = require_stackDelete(),
	    stackGet = require_stackGet(),
	    stackHas = require_stackHas(),
	    stackSet = require_stackSet();

	/**
	 * Creates a stack cache object to store key-value pairs.
	 *
	 * @private
	 * @constructor
	 * @param {Array} [entries] The key-value pairs to cache.
	 */
	function Stack(entries) {
	  var data = this.__data__ = new ListCache(entries);
	  this.size = data.size;
	}

	// Add methods to `Stack`.
	Stack.prototype.clear = stackClear;
	Stack.prototype['delete'] = stackDelete;
	Stack.prototype.get = stackGet;
	Stack.prototype.has = stackHas;
	Stack.prototype.set = stackSet;

	_Stack = Stack;
	return _Stack;
}

/**
 * A specialized version of `_.forEach` for arrays without support for
 * iteratee shorthands.
 *
 * @private
 * @param {Array} [array] The array to iterate over.
 * @param {Function} iteratee The function invoked per iteration.
 * @returns {Array} Returns `array`.
 */

var _arrayEach;
var hasRequired_arrayEach;

function require_arrayEach () {
	if (hasRequired_arrayEach) return _arrayEach;
	hasRequired_arrayEach = 1;
	function arrayEach(array, iteratee) {
	  var index = -1,
	      length = array == null ? 0 : array.length;

	  while (++index < length) {
	    if (iteratee(array[index], index, array) === false) {
	      break;
	    }
	  }
	  return array;
	}

	_arrayEach = arrayEach;
	return _arrayEach;
}

var _defineProperty;
var hasRequired_defineProperty;

function require_defineProperty () {
	if (hasRequired_defineProperty) return _defineProperty;
	hasRequired_defineProperty = 1;
	var getNative = require_getNative();

	var defineProperty = (function() {
	  try {
	    var func = getNative(Object, 'defineProperty');
	    func({}, '', {});
	    return func;
	  } catch (e) {}
	}());

	_defineProperty = defineProperty;
	return _defineProperty;
}

var _baseAssignValue;
var hasRequired_baseAssignValue;

function require_baseAssignValue () {
	if (hasRequired_baseAssignValue) return _baseAssignValue;
	hasRequired_baseAssignValue = 1;
	var defineProperty = require_defineProperty();

	/**
	 * The base implementation of `assignValue` and `assignMergeValue` without
	 * value checks.
	 *
	 * @private
	 * @param {Object} object The object to modify.
	 * @param {string} key The key of the property to assign.
	 * @param {*} value The value to assign.
	 */
	function baseAssignValue(object, key, value) {
	  if (key == '__proto__' && defineProperty) {
	    defineProperty(object, key, {
	      'configurable': true,
	      'enumerable': true,
	      'value': value,
	      'writable': true
	    });
	  } else {
	    object[key] = value;
	  }
	}

	_baseAssignValue = baseAssignValue;
	return _baseAssignValue;
}

var _assignValue;
var hasRequired_assignValue;

function require_assignValue () {
	if (hasRequired_assignValue) return _assignValue;
	hasRequired_assignValue = 1;
	var baseAssignValue = require_baseAssignValue(),
	    eq = requireEq();

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/**
	 * Assigns `value` to `key` of `object` if the existing value is not equivalent
	 * using [`SameValueZero`](http://ecma-international.org/ecma-262/7.0/#sec-samevaluezero)
	 * for equality comparisons.
	 *
	 * @private
	 * @param {Object} object The object to modify.
	 * @param {string} key The key of the property to assign.
	 * @param {*} value The value to assign.
	 */
	function assignValue(object, key, value) {
	  var objValue = object[key];
	  if (!(hasOwnProperty.call(object, key) && eq(objValue, value)) ||
	      (value === undefined && !(key in object))) {
	    baseAssignValue(object, key, value);
	  }
	}

	_assignValue = assignValue;
	return _assignValue;
}

var _copyObject;
var hasRequired_copyObject;

function require_copyObject () {
	if (hasRequired_copyObject) return _copyObject;
	hasRequired_copyObject = 1;
	var assignValue = require_assignValue(),
	    baseAssignValue = require_baseAssignValue();

	/**
	 * Copies properties of `source` to `object`.
	 *
	 * @private
	 * @param {Object} source The object to copy properties from.
	 * @param {Array} props The property identifiers to copy.
	 * @param {Object} [object={}] The object to copy properties to.
	 * @param {Function} [customizer] The function to customize copied values.
	 * @returns {Object} Returns `object`.
	 */
	function copyObject(source, props, object, customizer) {
	  var isNew = !object;
	  object || (object = {});

	  var index = -1,
	      length = props.length;

	  while (++index < length) {
	    var key = props[index];

	    var newValue = customizer
	      ? customizer(object[key], source[key], key, object, source)
	      : undefined;

	    if (newValue === undefined) {
	      newValue = source[key];
	    }
	    if (isNew) {
	      baseAssignValue(object, key, newValue);
	    } else {
	      assignValue(object, key, newValue);
	    }
	  }
	  return object;
	}

	_copyObject = copyObject;
	return _copyObject;
}

/**
 * The base implementation of `_.times` without support for iteratee shorthands
 * or max array length checks.
 *
 * @private
 * @param {number} n The number of times to invoke `iteratee`.
 * @param {Function} iteratee The function invoked per iteration.
 * @returns {Array} Returns the array of results.
 */

var _baseTimes;
var hasRequired_baseTimes;

function require_baseTimes () {
	if (hasRequired_baseTimes) return _baseTimes;
	hasRequired_baseTimes = 1;
	function baseTimes(n, iteratee) {
	  var index = -1,
	      result = Array(n);

	  while (++index < n) {
	    result[index] = iteratee(index);
	  }
	  return result;
	}

	_baseTimes = baseTimes;
	return _baseTimes;
}

/**
 * Checks if `value` is object-like. A value is object-like if it's not `null`
 * and has a `typeof` result of "object".
 *
 * @static
 * @memberOf _
 * @since 4.0.0
 * @category Lang
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is object-like, else `false`.
 * @example
 *
 * _.isObjectLike({});
 * // => true
 *
 * _.isObjectLike([1, 2, 3]);
 * // => true
 *
 * _.isObjectLike(_.noop);
 * // => false
 *
 * _.isObjectLike(null);
 * // => false
 */

var isObjectLike_1;
var hasRequiredIsObjectLike;

function requireIsObjectLike () {
	if (hasRequiredIsObjectLike) return isObjectLike_1;
	hasRequiredIsObjectLike = 1;
	function isObjectLike(value) {
	  return value != null && typeof value == 'object';
	}

	isObjectLike_1 = isObjectLike;
	return isObjectLike_1;
}

var _baseIsArguments;
var hasRequired_baseIsArguments;

function require_baseIsArguments () {
	if (hasRequired_baseIsArguments) return _baseIsArguments;
	hasRequired_baseIsArguments = 1;
	var baseGetTag = require_baseGetTag(),
	    isObjectLike = requireIsObjectLike();

	/** `Object#toString` result references. */
	var argsTag = '[object Arguments]';

	/**
	 * The base implementation of `_.isArguments`.
	 *
	 * @private
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is an `arguments` object,
	 */
	function baseIsArguments(value) {
	  return isObjectLike(value) && baseGetTag(value) == argsTag;
	}

	_baseIsArguments = baseIsArguments;
	return _baseIsArguments;
}

var isArguments_1;
var hasRequiredIsArguments;

function requireIsArguments () {
	if (hasRequiredIsArguments) return isArguments_1;
	hasRequiredIsArguments = 1;
	var baseIsArguments = require_baseIsArguments(),
	    isObjectLike = requireIsObjectLike();

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/** Built-in value references. */
	var propertyIsEnumerable = objectProto.propertyIsEnumerable;

	/**
	 * Checks if `value` is likely an `arguments` object.
	 *
	 * @static
	 * @memberOf _
	 * @since 0.1.0
	 * @category Lang
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is an `arguments` object,
	 *  else `false`.
	 * @example
	 *
	 * _.isArguments(function() { return arguments; }());
	 * // => true
	 *
	 * _.isArguments([1, 2, 3]);
	 * // => false
	 */
	var isArguments = baseIsArguments(function() { return arguments; }()) ? baseIsArguments : function(value) {
	  return isObjectLike(value) && hasOwnProperty.call(value, 'callee') &&
	    !propertyIsEnumerable.call(value, 'callee');
	};

	isArguments_1 = isArguments;
	return isArguments_1;
}

/**
 * Checks if `value` is classified as an `Array` object.
 *
 * @static
 * @memberOf _
 * @since 0.1.0
 * @category Lang
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is an array, else `false`.
 * @example
 *
 * _.isArray([1, 2, 3]);
 * // => true
 *
 * _.isArray(document.body.children);
 * // => false
 *
 * _.isArray('abc');
 * // => false
 *
 * _.isArray(_.noop);
 * // => false
 */

var isArray_1;
var hasRequiredIsArray;

function requireIsArray () {
	if (hasRequiredIsArray) return isArray_1;
	hasRequiredIsArray = 1;
	var isArray = Array.isArray;

	isArray_1 = isArray;
	return isArray_1;
}

var isBuffer = {exports: {}};

/**
 * This method returns `false`.
 *
 * @static
 * @memberOf _
 * @since 4.13.0
 * @category Util
 * @returns {boolean} Returns `false`.
 * @example
 *
 * _.times(2, _.stubFalse);
 * // => [false, false]
 */

var stubFalse_1;
var hasRequiredStubFalse;

function requireStubFalse () {
	if (hasRequiredStubFalse) return stubFalse_1;
	hasRequiredStubFalse = 1;
	function stubFalse() {
	  return false;
	}

	stubFalse_1 = stubFalse;
	return stubFalse_1;
}

isBuffer.exports;

var hasRequiredIsBuffer;

function requireIsBuffer () {
	if (hasRequiredIsBuffer) return isBuffer.exports;
	hasRequiredIsBuffer = 1;
	(function (module, exports) {
		var root = require_root(),
		    stubFalse = requireStubFalse();

		/** Detect free variable `exports`. */
		var freeExports = exports && !exports.nodeType && exports;

		/** Detect free variable `module`. */
		var freeModule = freeExports && 'object' == 'object' && module && !module.nodeType && module;

		/** Detect the popular CommonJS extension `module.exports`. */
		var moduleExports = freeModule && freeModule.exports === freeExports;

		/** Built-in value references. */
		var Buffer = moduleExports ? root.Buffer : undefined;

		/* Built-in method references for those with the same name as other `lodash` methods. */
		var nativeIsBuffer = Buffer ? Buffer.isBuffer : undefined;

		/**
		 * Checks if `value` is a buffer.
		 *
		 * @static
		 * @memberOf _
		 * @since 4.3.0
		 * @category Lang
		 * @param {*} value The value to check.
		 * @returns {boolean} Returns `true` if `value` is a buffer, else `false`.
		 * @example
		 *
		 * _.isBuffer(new Buffer(2));
		 * // => true
		 *
		 * _.isBuffer(new Uint8Array(2));
		 * // => false
		 */
		var isBuffer = nativeIsBuffer || stubFalse;

		module.exports = isBuffer; 
	} (isBuffer, isBuffer.exports));
	return isBuffer.exports;
}

/** Used as references for various `Number` constants. */

var _isIndex;
var hasRequired_isIndex;

function require_isIndex () {
	if (hasRequired_isIndex) return _isIndex;
	hasRequired_isIndex = 1;
	var MAX_SAFE_INTEGER = 9007199254740991;

	/** Used to detect unsigned integer values. */
	var reIsUint = /^(?:0|[1-9]\d*)$/;

	/**
	 * Checks if `value` is a valid array-like index.
	 *
	 * @private
	 * @param {*} value The value to check.
	 * @param {number} [length=MAX_SAFE_INTEGER] The upper bounds of a valid index.
	 * @returns {boolean} Returns `true` if `value` is a valid index, else `false`.
	 */
	function isIndex(value, length) {
	  var type = typeof value;
	  length = length == null ? MAX_SAFE_INTEGER : length;

	  return !!length &&
	    (type == 'number' ||
	      (type != 'symbol' && reIsUint.test(value))) &&
	        (value > -1 && value % 1 == 0 && value < length);
	}

	_isIndex = isIndex;
	return _isIndex;
}

/** Used as references for various `Number` constants. */

var isLength_1;
var hasRequiredIsLength;

function requireIsLength () {
	if (hasRequiredIsLength) return isLength_1;
	hasRequiredIsLength = 1;
	var MAX_SAFE_INTEGER = 9007199254740991;

	/**
	 * Checks if `value` is a valid array-like length.
	 *
	 * **Note:** This method is loosely based on
	 * [`ToLength`](http://ecma-international.org/ecma-262/7.0/#sec-tolength).
	 *
	 * @static
	 * @memberOf _
	 * @since 4.0.0
	 * @category Lang
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a valid length, else `false`.
	 * @example
	 *
	 * _.isLength(3);
	 * // => true
	 *
	 * _.isLength(Number.MIN_VALUE);
	 * // => false
	 *
	 * _.isLength(Infinity);
	 * // => false
	 *
	 * _.isLength('3');
	 * // => false
	 */
	function isLength(value) {
	  return typeof value == 'number' &&
	    value > -1 && value % 1 == 0 && value <= MAX_SAFE_INTEGER;
	}

	isLength_1 = isLength;
	return isLength_1;
}

var _baseIsTypedArray;
var hasRequired_baseIsTypedArray;

function require_baseIsTypedArray () {
	if (hasRequired_baseIsTypedArray) return _baseIsTypedArray;
	hasRequired_baseIsTypedArray = 1;
	var baseGetTag = require_baseGetTag(),
	    isLength = requireIsLength(),
	    isObjectLike = requireIsObjectLike();

	/** `Object#toString` result references. */
	var argsTag = '[object Arguments]',
	    arrayTag = '[object Array]',
	    boolTag = '[object Boolean]',
	    dateTag = '[object Date]',
	    errorTag = '[object Error]',
	    funcTag = '[object Function]',
	    mapTag = '[object Map]',
	    numberTag = '[object Number]',
	    objectTag = '[object Object]',
	    regexpTag = '[object RegExp]',
	    setTag = '[object Set]',
	    stringTag = '[object String]',
	    weakMapTag = '[object WeakMap]';

	var arrayBufferTag = '[object ArrayBuffer]',
	    dataViewTag = '[object DataView]',
	    float32Tag = '[object Float32Array]',
	    float64Tag = '[object Float64Array]',
	    int8Tag = '[object Int8Array]',
	    int16Tag = '[object Int16Array]',
	    int32Tag = '[object Int32Array]',
	    uint8Tag = '[object Uint8Array]',
	    uint8ClampedTag = '[object Uint8ClampedArray]',
	    uint16Tag = '[object Uint16Array]',
	    uint32Tag = '[object Uint32Array]';

	/** Used to identify `toStringTag` values of typed arrays. */
	var typedArrayTags = {};
	typedArrayTags[float32Tag] = typedArrayTags[float64Tag] =
	typedArrayTags[int8Tag] = typedArrayTags[int16Tag] =
	typedArrayTags[int32Tag] = typedArrayTags[uint8Tag] =
	typedArrayTags[uint8ClampedTag] = typedArrayTags[uint16Tag] =
	typedArrayTags[uint32Tag] = true;
	typedArrayTags[argsTag] = typedArrayTags[arrayTag] =
	typedArrayTags[arrayBufferTag] = typedArrayTags[boolTag] =
	typedArrayTags[dataViewTag] = typedArrayTags[dateTag] =
	typedArrayTags[errorTag] = typedArrayTags[funcTag] =
	typedArrayTags[mapTag] = typedArrayTags[numberTag] =
	typedArrayTags[objectTag] = typedArrayTags[regexpTag] =
	typedArrayTags[setTag] = typedArrayTags[stringTag] =
	typedArrayTags[weakMapTag] = false;

	/**
	 * The base implementation of `_.isTypedArray` without Node.js optimizations.
	 *
	 * @private
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a typed array, else `false`.
	 */
	function baseIsTypedArray(value) {
	  return isObjectLike(value) &&
	    isLength(value.length) && !!typedArrayTags[baseGetTag(value)];
	}

	_baseIsTypedArray = baseIsTypedArray;
	return _baseIsTypedArray;
}

/**
 * The base implementation of `_.unary` without support for storing metadata.
 *
 * @private
 * @param {Function} func The function to cap arguments for.
 * @returns {Function} Returns the new capped function.
 */

var _baseUnary;
var hasRequired_baseUnary;

function require_baseUnary () {
	if (hasRequired_baseUnary) return _baseUnary;
	hasRequired_baseUnary = 1;
	function baseUnary(func) {
	  return function(value) {
	    return func(value);
	  };
	}

	_baseUnary = baseUnary;
	return _baseUnary;
}

var _nodeUtil = {exports: {}};

_nodeUtil.exports;

var hasRequired_nodeUtil;

function require_nodeUtil () {
	if (hasRequired_nodeUtil) return _nodeUtil.exports;
	hasRequired_nodeUtil = 1;
	(function (module, exports) {
		var freeGlobal = require_freeGlobal();

		/** Detect free variable `exports`. */
		var freeExports = exports && !exports.nodeType && exports;

		/** Detect free variable `module`. */
		var freeModule = freeExports && 'object' == 'object' && module && !module.nodeType && module;

		/** Detect the popular CommonJS extension `module.exports`. */
		var moduleExports = freeModule && freeModule.exports === freeExports;

		/** Detect free variable `process` from Node.js. */
		var freeProcess = moduleExports && freeGlobal.process;

		/** Used to access faster Node.js helpers. */
		var nodeUtil = (function() {
		  try {
		    // Use `util.types` for Node.js 10+.
		    var types = freeModule && freeModule.require && freeModule.require('util').types;

		    if (types) {
		      return types;
		    }

		    // Legacy `process.binding('util')` for Node.js < 10.
		    return freeProcess && freeProcess.binding && freeProcess.binding('util');
		  } catch (e) {}
		}());

		module.exports = nodeUtil; 
	} (_nodeUtil, _nodeUtil.exports));
	return _nodeUtil.exports;
}

var isTypedArray_1;
var hasRequiredIsTypedArray;

function requireIsTypedArray () {
	if (hasRequiredIsTypedArray) return isTypedArray_1;
	hasRequiredIsTypedArray = 1;
	var baseIsTypedArray = require_baseIsTypedArray(),
	    baseUnary = require_baseUnary(),
	    nodeUtil = require_nodeUtil();

	/* Node.js helper references. */
	var nodeIsTypedArray = nodeUtil && nodeUtil.isTypedArray;

	/**
	 * Checks if `value` is classified as a typed array.
	 *
	 * @static
	 * @memberOf _
	 * @since 3.0.0
	 * @category Lang
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a typed array, else `false`.
	 * @example
	 *
	 * _.isTypedArray(new Uint8Array);
	 * // => true
	 *
	 * _.isTypedArray([]);
	 * // => false
	 */
	var isTypedArray = nodeIsTypedArray ? baseUnary(nodeIsTypedArray) : baseIsTypedArray;

	isTypedArray_1 = isTypedArray;
	return isTypedArray_1;
}

var _arrayLikeKeys;
var hasRequired_arrayLikeKeys;

function require_arrayLikeKeys () {
	if (hasRequired_arrayLikeKeys) return _arrayLikeKeys;
	hasRequired_arrayLikeKeys = 1;
	var baseTimes = require_baseTimes(),
	    isArguments = requireIsArguments(),
	    isArray = requireIsArray(),
	    isBuffer = requireIsBuffer(),
	    isIndex = require_isIndex(),
	    isTypedArray = requireIsTypedArray();

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/**
	 * Creates an array of the enumerable property names of the array-like `value`.
	 *
	 * @private
	 * @param {*} value The value to query.
	 * @param {boolean} inherited Specify returning inherited property names.
	 * @returns {Array} Returns the array of property names.
	 */
	function arrayLikeKeys(value, inherited) {
	  var isArr = isArray(value),
	      isArg = !isArr && isArguments(value),
	      isBuff = !isArr && !isArg && isBuffer(value),
	      isType = !isArr && !isArg && !isBuff && isTypedArray(value),
	      skipIndexes = isArr || isArg || isBuff || isType,
	      result = skipIndexes ? baseTimes(value.length, String) : [],
	      length = result.length;

	  for (var key in value) {
	    if ((inherited || hasOwnProperty.call(value, key)) &&
	        !(skipIndexes && (
	           // Safari 9 has enumerable `arguments.length` in strict mode.
	           key == 'length' ||
	           // Node.js 0.10 has enumerable non-index properties on buffers.
	           (isBuff && (key == 'offset' || key == 'parent')) ||
	           // PhantomJS 2 has enumerable non-index properties on typed arrays.
	           (isType && (key == 'buffer' || key == 'byteLength' || key == 'byteOffset')) ||
	           // Skip index properties.
	           isIndex(key, length)
	        ))) {
	      result.push(key);
	    }
	  }
	  return result;
	}

	_arrayLikeKeys = arrayLikeKeys;
	return _arrayLikeKeys;
}

/** Used for built-in method references. */

var _isPrototype;
var hasRequired_isPrototype;

function require_isPrototype () {
	if (hasRequired_isPrototype) return _isPrototype;
	hasRequired_isPrototype = 1;
	var objectProto = Object.prototype;

	/**
	 * Checks if `value` is likely a prototype object.
	 *
	 * @private
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a prototype, else `false`.
	 */
	function isPrototype(value) {
	  var Ctor = value && value.constructor,
	      proto = (typeof Ctor == 'function' && Ctor.prototype) || objectProto;

	  return value === proto;
	}

	_isPrototype = isPrototype;
	return _isPrototype;
}

/**
 * Creates a unary function that invokes `func` with its argument transformed.
 *
 * @private
 * @param {Function} func The function to wrap.
 * @param {Function} transform The argument transform.
 * @returns {Function} Returns the new function.
 */

var _overArg;
var hasRequired_overArg;

function require_overArg () {
	if (hasRequired_overArg) return _overArg;
	hasRequired_overArg = 1;
	function overArg(func, transform) {
	  return function(arg) {
	    return func(transform(arg));
	  };
	}

	_overArg = overArg;
	return _overArg;
}

var _nativeKeys;
var hasRequired_nativeKeys;

function require_nativeKeys () {
	if (hasRequired_nativeKeys) return _nativeKeys;
	hasRequired_nativeKeys = 1;
	var overArg = require_overArg();

	/* Built-in method references for those with the same name as other `lodash` methods. */
	var nativeKeys = overArg(Object.keys, Object);

	_nativeKeys = nativeKeys;
	return _nativeKeys;
}

var _baseKeys;
var hasRequired_baseKeys;

function require_baseKeys () {
	if (hasRequired_baseKeys) return _baseKeys;
	hasRequired_baseKeys = 1;
	var isPrototype = require_isPrototype(),
	    nativeKeys = require_nativeKeys();

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/**
	 * The base implementation of `_.keys` which doesn't treat sparse arrays as dense.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @returns {Array} Returns the array of property names.
	 */
	function baseKeys(object) {
	  if (!isPrototype(object)) {
	    return nativeKeys(object);
	  }
	  var result = [];
	  for (var key in Object(object)) {
	    if (hasOwnProperty.call(object, key) && key != 'constructor') {
	      result.push(key);
	    }
	  }
	  return result;
	}

	_baseKeys = baseKeys;
	return _baseKeys;
}

var isArrayLike_1;
var hasRequiredIsArrayLike;

function requireIsArrayLike () {
	if (hasRequiredIsArrayLike) return isArrayLike_1;
	hasRequiredIsArrayLike = 1;
	var isFunction = requireIsFunction(),
	    isLength = requireIsLength();

	/**
	 * Checks if `value` is array-like. A value is considered array-like if it's
	 * not a function and has a `value.length` that's an integer greater than or
	 * equal to `0` and less than or equal to `Number.MAX_SAFE_INTEGER`.
	 *
	 * @static
	 * @memberOf _
	 * @since 4.0.0
	 * @category Lang
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is array-like, else `false`.
	 * @example
	 *
	 * _.isArrayLike([1, 2, 3]);
	 * // => true
	 *
	 * _.isArrayLike(document.body.children);
	 * // => true
	 *
	 * _.isArrayLike('abc');
	 * // => true
	 *
	 * _.isArrayLike(_.noop);
	 * // => false
	 */
	function isArrayLike(value) {
	  return value != null && isLength(value.length) && !isFunction(value);
	}

	isArrayLike_1 = isArrayLike;
	return isArrayLike_1;
}

var keys_1;
var hasRequiredKeys;

function requireKeys () {
	if (hasRequiredKeys) return keys_1;
	hasRequiredKeys = 1;
	var arrayLikeKeys = require_arrayLikeKeys(),
	    baseKeys = require_baseKeys(),
	    isArrayLike = requireIsArrayLike();

	/**
	 * Creates an array of the own enumerable property names of `object`.
	 *
	 * **Note:** Non-object values are coerced to objects. See the
	 * [ES spec](http://ecma-international.org/ecma-262/7.0/#sec-object.keys)
	 * for more details.
	 *
	 * @static
	 * @since 0.1.0
	 * @memberOf _
	 * @category Object
	 * @param {Object} object The object to query.
	 * @returns {Array} Returns the array of property names.
	 * @example
	 *
	 * function Foo() {
	 *   this.a = 1;
	 *   this.b = 2;
	 * }
	 *
	 * Foo.prototype.c = 3;
	 *
	 * _.keys(new Foo);
	 * // => ['a', 'b'] (iteration order is not guaranteed)
	 *
	 * _.keys('hi');
	 * // => ['0', '1']
	 */
	function keys(object) {
	  return isArrayLike(object) ? arrayLikeKeys(object) : baseKeys(object);
	}

	keys_1 = keys;
	return keys_1;
}

var _baseAssign;
var hasRequired_baseAssign;

function require_baseAssign () {
	if (hasRequired_baseAssign) return _baseAssign;
	hasRequired_baseAssign = 1;
	var copyObject = require_copyObject(),
	    keys = requireKeys();

	/**
	 * The base implementation of `_.assign` without support for multiple sources
	 * or `customizer` functions.
	 *
	 * @private
	 * @param {Object} object The destination object.
	 * @param {Object} source The source object.
	 * @returns {Object} Returns `object`.
	 */
	function baseAssign(object, source) {
	  return object && copyObject(source, keys(source), object);
	}

	_baseAssign = baseAssign;
	return _baseAssign;
}

/**
 * This function is like
 * [`Object.keys`](http://ecma-international.org/ecma-262/7.0/#sec-object.keys)
 * except that it includes inherited enumerable properties.
 *
 * @private
 * @param {Object} object The object to query.
 * @returns {Array} Returns the array of property names.
 */

var _nativeKeysIn;
var hasRequired_nativeKeysIn;

function require_nativeKeysIn () {
	if (hasRequired_nativeKeysIn) return _nativeKeysIn;
	hasRequired_nativeKeysIn = 1;
	function nativeKeysIn(object) {
	  var result = [];
	  if (object != null) {
	    for (var key in Object(object)) {
	      result.push(key);
	    }
	  }
	  return result;
	}

	_nativeKeysIn = nativeKeysIn;
	return _nativeKeysIn;
}

var _baseKeysIn;
var hasRequired_baseKeysIn;

function require_baseKeysIn () {
	if (hasRequired_baseKeysIn) return _baseKeysIn;
	hasRequired_baseKeysIn = 1;
	var isObject = requireIsObject(),
	    isPrototype = require_isPrototype(),
	    nativeKeysIn = require_nativeKeysIn();

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/**
	 * The base implementation of `_.keysIn` which doesn't treat sparse arrays as dense.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @returns {Array} Returns the array of property names.
	 */
	function baseKeysIn(object) {
	  if (!isObject(object)) {
	    return nativeKeysIn(object);
	  }
	  var isProto = isPrototype(object),
	      result = [];

	  for (var key in object) {
	    if (!(key == 'constructor' && (isProto || !hasOwnProperty.call(object, key)))) {
	      result.push(key);
	    }
	  }
	  return result;
	}

	_baseKeysIn = baseKeysIn;
	return _baseKeysIn;
}

var keysIn_1;
var hasRequiredKeysIn;

function requireKeysIn () {
	if (hasRequiredKeysIn) return keysIn_1;
	hasRequiredKeysIn = 1;
	var arrayLikeKeys = require_arrayLikeKeys(),
	    baseKeysIn = require_baseKeysIn(),
	    isArrayLike = requireIsArrayLike();

	/**
	 * Creates an array of the own and inherited enumerable property names of `object`.
	 *
	 * **Note:** Non-object values are coerced to objects.
	 *
	 * @static
	 * @memberOf _
	 * @since 3.0.0
	 * @category Object
	 * @param {Object} object The object to query.
	 * @returns {Array} Returns the array of property names.
	 * @example
	 *
	 * function Foo() {
	 *   this.a = 1;
	 *   this.b = 2;
	 * }
	 *
	 * Foo.prototype.c = 3;
	 *
	 * _.keysIn(new Foo);
	 * // => ['a', 'b', 'c'] (iteration order is not guaranteed)
	 */
	function keysIn(object) {
	  return isArrayLike(object) ? arrayLikeKeys(object, true) : baseKeysIn(object);
	}

	keysIn_1 = keysIn;
	return keysIn_1;
}

var _baseAssignIn;
var hasRequired_baseAssignIn;

function require_baseAssignIn () {
	if (hasRequired_baseAssignIn) return _baseAssignIn;
	hasRequired_baseAssignIn = 1;
	var copyObject = require_copyObject(),
	    keysIn = requireKeysIn();

	/**
	 * The base implementation of `_.assignIn` without support for multiple sources
	 * or `customizer` functions.
	 *
	 * @private
	 * @param {Object} object The destination object.
	 * @param {Object} source The source object.
	 * @returns {Object} Returns `object`.
	 */
	function baseAssignIn(object, source) {
	  return object && copyObject(source, keysIn(source), object);
	}

	_baseAssignIn = baseAssignIn;
	return _baseAssignIn;
}

var _cloneBuffer = {exports: {}};

_cloneBuffer.exports;

var hasRequired_cloneBuffer;

function require_cloneBuffer () {
	if (hasRequired_cloneBuffer) return _cloneBuffer.exports;
	hasRequired_cloneBuffer = 1;
	(function (module, exports) {
		var root = require_root();

		/** Detect free variable `exports`. */
		var freeExports = exports && !exports.nodeType && exports;

		/** Detect free variable `module`. */
		var freeModule = freeExports && 'object' == 'object' && module && !module.nodeType && module;

		/** Detect the popular CommonJS extension `module.exports`. */
		var moduleExports = freeModule && freeModule.exports === freeExports;

		/** Built-in value references. */
		var Buffer = moduleExports ? root.Buffer : undefined,
		    allocUnsafe = Buffer ? Buffer.allocUnsafe : undefined;

		/**
		 * Creates a clone of  `buffer`.
		 *
		 * @private
		 * @param {Buffer} buffer The buffer to clone.
		 * @param {boolean} [isDeep] Specify a deep clone.
		 * @returns {Buffer} Returns the cloned buffer.
		 */
		function cloneBuffer(buffer, isDeep) {
		  if (isDeep) {
		    return buffer.slice();
		  }
		  var length = buffer.length,
		      result = allocUnsafe ? allocUnsafe(length) : new buffer.constructor(length);

		  buffer.copy(result);
		  return result;
		}

		module.exports = cloneBuffer; 
	} (_cloneBuffer, _cloneBuffer.exports));
	return _cloneBuffer.exports;
}

/**
 * Copies the values of `source` to `array`.
 *
 * @private
 * @param {Array} source The array to copy values from.
 * @param {Array} [array=[]] The array to copy values to.
 * @returns {Array} Returns `array`.
 */

var _copyArray;
var hasRequired_copyArray;

function require_copyArray () {
	if (hasRequired_copyArray) return _copyArray;
	hasRequired_copyArray = 1;
	function copyArray(source, array) {
	  var index = -1,
	      length = source.length;

	  array || (array = Array(length));
	  while (++index < length) {
	    array[index] = source[index];
	  }
	  return array;
	}

	_copyArray = copyArray;
	return _copyArray;
}

/**
 * A specialized version of `_.filter` for arrays without support for
 * iteratee shorthands.
 *
 * @private
 * @param {Array} [array] The array to iterate over.
 * @param {Function} predicate The function invoked per iteration.
 * @returns {Array} Returns the new filtered array.
 */

var _arrayFilter;
var hasRequired_arrayFilter;

function require_arrayFilter () {
	if (hasRequired_arrayFilter) return _arrayFilter;
	hasRequired_arrayFilter = 1;
	function arrayFilter(array, predicate) {
	  var index = -1,
	      length = array == null ? 0 : array.length,
	      resIndex = 0,
	      result = [];

	  while (++index < length) {
	    var value = array[index];
	    if (predicate(value, index, array)) {
	      result[resIndex++] = value;
	    }
	  }
	  return result;
	}

	_arrayFilter = arrayFilter;
	return _arrayFilter;
}

/**
 * This method returns a new empty array.
 *
 * @static
 * @memberOf _
 * @since 4.13.0
 * @category Util
 * @returns {Array} Returns the new empty array.
 * @example
 *
 * var arrays = _.times(2, _.stubArray);
 *
 * console.log(arrays);
 * // => [[], []]
 *
 * console.log(arrays[0] === arrays[1]);
 * // => false
 */

var stubArray_1;
var hasRequiredStubArray;

function requireStubArray () {
	if (hasRequiredStubArray) return stubArray_1;
	hasRequiredStubArray = 1;
	function stubArray() {
	  return [];
	}

	stubArray_1 = stubArray;
	return stubArray_1;
}

var _getSymbols;
var hasRequired_getSymbols;

function require_getSymbols () {
	if (hasRequired_getSymbols) return _getSymbols;
	hasRequired_getSymbols = 1;
	var arrayFilter = require_arrayFilter(),
	    stubArray = requireStubArray();

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Built-in value references. */
	var propertyIsEnumerable = objectProto.propertyIsEnumerable;

	/* Built-in method references for those with the same name as other `lodash` methods. */
	var nativeGetSymbols = Object.getOwnPropertySymbols;

	/**
	 * Creates an array of the own enumerable symbols of `object`.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @returns {Array} Returns the array of symbols.
	 */
	var getSymbols = !nativeGetSymbols ? stubArray : function(object) {
	  if (object == null) {
	    return [];
	  }
	  object = Object(object);
	  return arrayFilter(nativeGetSymbols(object), function(symbol) {
	    return propertyIsEnumerable.call(object, symbol);
	  });
	};

	_getSymbols = getSymbols;
	return _getSymbols;
}

var _copySymbols;
var hasRequired_copySymbols;

function require_copySymbols () {
	if (hasRequired_copySymbols) return _copySymbols;
	hasRequired_copySymbols = 1;
	var copyObject = require_copyObject(),
	    getSymbols = require_getSymbols();

	/**
	 * Copies own symbols of `source` to `object`.
	 *
	 * @private
	 * @param {Object} source The object to copy symbols from.
	 * @param {Object} [object={}] The object to copy symbols to.
	 * @returns {Object} Returns `object`.
	 */
	function copySymbols(source, object) {
	  return copyObject(source, getSymbols(source), object);
	}

	_copySymbols = copySymbols;
	return _copySymbols;
}

/**
 * Appends the elements of `values` to `array`.
 *
 * @private
 * @param {Array} array The array to modify.
 * @param {Array} values The values to append.
 * @returns {Array} Returns `array`.
 */

var _arrayPush;
var hasRequired_arrayPush;

function require_arrayPush () {
	if (hasRequired_arrayPush) return _arrayPush;
	hasRequired_arrayPush = 1;
	function arrayPush(array, values) {
	  var index = -1,
	      length = values.length,
	      offset = array.length;

	  while (++index < length) {
	    array[offset + index] = values[index];
	  }
	  return array;
	}

	_arrayPush = arrayPush;
	return _arrayPush;
}

var _getPrototype;
var hasRequired_getPrototype;

function require_getPrototype () {
	if (hasRequired_getPrototype) return _getPrototype;
	hasRequired_getPrototype = 1;
	var overArg = require_overArg();

	/** Built-in value references. */
	var getPrototype = overArg(Object.getPrototypeOf, Object);

	_getPrototype = getPrototype;
	return _getPrototype;
}

var _getSymbolsIn;
var hasRequired_getSymbolsIn;

function require_getSymbolsIn () {
	if (hasRequired_getSymbolsIn) return _getSymbolsIn;
	hasRequired_getSymbolsIn = 1;
	var arrayPush = require_arrayPush(),
	    getPrototype = require_getPrototype(),
	    getSymbols = require_getSymbols(),
	    stubArray = requireStubArray();

	/* Built-in method references for those with the same name as other `lodash` methods. */
	var nativeGetSymbols = Object.getOwnPropertySymbols;

	/**
	 * Creates an array of the own and inherited enumerable symbols of `object`.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @returns {Array} Returns the array of symbols.
	 */
	var getSymbolsIn = !nativeGetSymbols ? stubArray : function(object) {
	  var result = [];
	  while (object) {
	    arrayPush(result, getSymbols(object));
	    object = getPrototype(object);
	  }
	  return result;
	};

	_getSymbolsIn = getSymbolsIn;
	return _getSymbolsIn;
}

var _copySymbolsIn;
var hasRequired_copySymbolsIn;

function require_copySymbolsIn () {
	if (hasRequired_copySymbolsIn) return _copySymbolsIn;
	hasRequired_copySymbolsIn = 1;
	var copyObject = require_copyObject(),
	    getSymbolsIn = require_getSymbolsIn();

	/**
	 * Copies own and inherited symbols of `source` to `object`.
	 *
	 * @private
	 * @param {Object} source The object to copy symbols from.
	 * @param {Object} [object={}] The object to copy symbols to.
	 * @returns {Object} Returns `object`.
	 */
	function copySymbolsIn(source, object) {
	  return copyObject(source, getSymbolsIn(source), object);
	}

	_copySymbolsIn = copySymbolsIn;
	return _copySymbolsIn;
}

var _baseGetAllKeys;
var hasRequired_baseGetAllKeys;

function require_baseGetAllKeys () {
	if (hasRequired_baseGetAllKeys) return _baseGetAllKeys;
	hasRequired_baseGetAllKeys = 1;
	var arrayPush = require_arrayPush(),
	    isArray = requireIsArray();

	/**
	 * The base implementation of `getAllKeys` and `getAllKeysIn` which uses
	 * `keysFunc` and `symbolsFunc` to get the enumerable property names and
	 * symbols of `object`.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @param {Function} keysFunc The function to get the keys of `object`.
	 * @param {Function} symbolsFunc The function to get the symbols of `object`.
	 * @returns {Array} Returns the array of property names and symbols.
	 */
	function baseGetAllKeys(object, keysFunc, symbolsFunc) {
	  var result = keysFunc(object);
	  return isArray(object) ? result : arrayPush(result, symbolsFunc(object));
	}

	_baseGetAllKeys = baseGetAllKeys;
	return _baseGetAllKeys;
}

var _getAllKeys;
var hasRequired_getAllKeys;

function require_getAllKeys () {
	if (hasRequired_getAllKeys) return _getAllKeys;
	hasRequired_getAllKeys = 1;
	var baseGetAllKeys = require_baseGetAllKeys(),
	    getSymbols = require_getSymbols(),
	    keys = requireKeys();

	/**
	 * Creates an array of own enumerable property names and symbols of `object`.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @returns {Array} Returns the array of property names and symbols.
	 */
	function getAllKeys(object) {
	  return baseGetAllKeys(object, keys, getSymbols);
	}

	_getAllKeys = getAllKeys;
	return _getAllKeys;
}

var _getAllKeysIn;
var hasRequired_getAllKeysIn;

function require_getAllKeysIn () {
	if (hasRequired_getAllKeysIn) return _getAllKeysIn;
	hasRequired_getAllKeysIn = 1;
	var baseGetAllKeys = require_baseGetAllKeys(),
	    getSymbolsIn = require_getSymbolsIn(),
	    keysIn = requireKeysIn();

	/**
	 * Creates an array of own and inherited enumerable property names and
	 * symbols of `object`.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @returns {Array} Returns the array of property names and symbols.
	 */
	function getAllKeysIn(object) {
	  return baseGetAllKeys(object, keysIn, getSymbolsIn);
	}

	_getAllKeysIn = getAllKeysIn;
	return _getAllKeysIn;
}

var _DataView;
var hasRequired_DataView;

function require_DataView () {
	if (hasRequired_DataView) return _DataView;
	hasRequired_DataView = 1;
	var getNative = require_getNative(),
	    root = require_root();

	/* Built-in method references that are verified to be native. */
	var DataView = getNative(root, 'DataView');

	_DataView = DataView;
	return _DataView;
}

var _Promise;
var hasRequired_Promise;

function require_Promise () {
	if (hasRequired_Promise) return _Promise;
	hasRequired_Promise = 1;
	var getNative = require_getNative(),
	    root = require_root();

	/* Built-in method references that are verified to be native. */
	var Promise = getNative(root, 'Promise');

	_Promise = Promise;
	return _Promise;
}

var _Set;
var hasRequired_Set;

function require_Set () {
	if (hasRequired_Set) return _Set;
	hasRequired_Set = 1;
	var getNative = require_getNative(),
	    root = require_root();

	/* Built-in method references that are verified to be native. */
	var Set = getNative(root, 'Set');

	_Set = Set;
	return _Set;
}

var _WeakMap;
var hasRequired_WeakMap;

function require_WeakMap () {
	if (hasRequired_WeakMap) return _WeakMap;
	hasRequired_WeakMap = 1;
	var getNative = require_getNative(),
	    root = require_root();

	/* Built-in method references that are verified to be native. */
	var WeakMap = getNative(root, 'WeakMap');

	_WeakMap = WeakMap;
	return _WeakMap;
}

var _getTag;
var hasRequired_getTag;

function require_getTag () {
	if (hasRequired_getTag) return _getTag;
	hasRequired_getTag = 1;
	var DataView = require_DataView(),
	    Map = require_Map(),
	    Promise = require_Promise(),
	    Set = require_Set(),
	    WeakMap = require_WeakMap(),
	    baseGetTag = require_baseGetTag(),
	    toSource = require_toSource();

	/** `Object#toString` result references. */
	var mapTag = '[object Map]',
	    objectTag = '[object Object]',
	    promiseTag = '[object Promise]',
	    setTag = '[object Set]',
	    weakMapTag = '[object WeakMap]';

	var dataViewTag = '[object DataView]';

	/** Used to detect maps, sets, and weakmaps. */
	var dataViewCtorString = toSource(DataView),
	    mapCtorString = toSource(Map),
	    promiseCtorString = toSource(Promise),
	    setCtorString = toSource(Set),
	    weakMapCtorString = toSource(WeakMap);

	/**
	 * Gets the `toStringTag` of `value`.
	 *
	 * @private
	 * @param {*} value The value to query.
	 * @returns {string} Returns the `toStringTag`.
	 */
	var getTag = baseGetTag;

	// Fallback for data views, maps, sets, and weak maps in IE 11 and promises in Node.js < 6.
	if ((DataView && getTag(new DataView(new ArrayBuffer(1))) != dataViewTag) ||
	    (Map && getTag(new Map) != mapTag) ||
	    (Promise && getTag(Promise.resolve()) != promiseTag) ||
	    (Set && getTag(new Set) != setTag) ||
	    (WeakMap && getTag(new WeakMap) != weakMapTag)) {
	  getTag = function(value) {
	    var result = baseGetTag(value),
	        Ctor = result == objectTag ? value.constructor : undefined,
	        ctorString = Ctor ? toSource(Ctor) : '';

	    if (ctorString) {
	      switch (ctorString) {
	        case dataViewCtorString: return dataViewTag;
	        case mapCtorString: return mapTag;
	        case promiseCtorString: return promiseTag;
	        case setCtorString: return setTag;
	        case weakMapCtorString: return weakMapTag;
	      }
	    }
	    return result;
	  };
	}

	_getTag = getTag;
	return _getTag;
}

/** Used for built-in method references. */

var _initCloneArray;
var hasRequired_initCloneArray;

function require_initCloneArray () {
	if (hasRequired_initCloneArray) return _initCloneArray;
	hasRequired_initCloneArray = 1;
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/**
	 * Initializes an array clone.
	 *
	 * @private
	 * @param {Array} array The array to clone.
	 * @returns {Array} Returns the initialized clone.
	 */
	function initCloneArray(array) {
	  var length = array.length,
	      result = new array.constructor(length);

	  // Add properties assigned by `RegExp#exec`.
	  if (length && typeof array[0] == 'string' && hasOwnProperty.call(array, 'index')) {
	    result.index = array.index;
	    result.input = array.input;
	  }
	  return result;
	}

	_initCloneArray = initCloneArray;
	return _initCloneArray;
}

var _Uint8Array;
var hasRequired_Uint8Array;

function require_Uint8Array () {
	if (hasRequired_Uint8Array) return _Uint8Array;
	hasRequired_Uint8Array = 1;
	var root = require_root();

	/** Built-in value references. */
	var Uint8Array = root.Uint8Array;

	_Uint8Array = Uint8Array;
	return _Uint8Array;
}

var _cloneArrayBuffer;
var hasRequired_cloneArrayBuffer;

function require_cloneArrayBuffer () {
	if (hasRequired_cloneArrayBuffer) return _cloneArrayBuffer;
	hasRequired_cloneArrayBuffer = 1;
	var Uint8Array = require_Uint8Array();

	/**
	 * Creates a clone of `arrayBuffer`.
	 *
	 * @private
	 * @param {ArrayBuffer} arrayBuffer The array buffer to clone.
	 * @returns {ArrayBuffer} Returns the cloned array buffer.
	 */
	function cloneArrayBuffer(arrayBuffer) {
	  var result = new arrayBuffer.constructor(arrayBuffer.byteLength);
	  new Uint8Array(result).set(new Uint8Array(arrayBuffer));
	  return result;
	}

	_cloneArrayBuffer = cloneArrayBuffer;
	return _cloneArrayBuffer;
}

var _cloneDataView;
var hasRequired_cloneDataView;

function require_cloneDataView () {
	if (hasRequired_cloneDataView) return _cloneDataView;
	hasRequired_cloneDataView = 1;
	var cloneArrayBuffer = require_cloneArrayBuffer();

	/**
	 * Creates a clone of `dataView`.
	 *
	 * @private
	 * @param {Object} dataView The data view to clone.
	 * @param {boolean} [isDeep] Specify a deep clone.
	 * @returns {Object} Returns the cloned data view.
	 */
	function cloneDataView(dataView, isDeep) {
	  var buffer = isDeep ? cloneArrayBuffer(dataView.buffer) : dataView.buffer;
	  return new dataView.constructor(buffer, dataView.byteOffset, dataView.byteLength);
	}

	_cloneDataView = cloneDataView;
	return _cloneDataView;
}

/** Used to match `RegExp` flags from their coerced string values. */

var _cloneRegExp;
var hasRequired_cloneRegExp;

function require_cloneRegExp () {
	if (hasRequired_cloneRegExp) return _cloneRegExp;
	hasRequired_cloneRegExp = 1;
	var reFlags = /\w*$/;

	/**
	 * Creates a clone of `regexp`.
	 *
	 * @private
	 * @param {Object} regexp The regexp to clone.
	 * @returns {Object} Returns the cloned regexp.
	 */
	function cloneRegExp(regexp) {
	  var result = new regexp.constructor(regexp.source, reFlags.exec(regexp));
	  result.lastIndex = regexp.lastIndex;
	  return result;
	}

	_cloneRegExp = cloneRegExp;
	return _cloneRegExp;
}

var _cloneSymbol;
var hasRequired_cloneSymbol;

function require_cloneSymbol () {
	if (hasRequired_cloneSymbol) return _cloneSymbol;
	hasRequired_cloneSymbol = 1;
	var Symbol = require_Symbol();

	/** Used to convert symbols to primitives and strings. */
	var symbolProto = Symbol ? Symbol.prototype : undefined,
	    symbolValueOf = symbolProto ? symbolProto.valueOf : undefined;

	/**
	 * Creates a clone of the `symbol` object.
	 *
	 * @private
	 * @param {Object} symbol The symbol object to clone.
	 * @returns {Object} Returns the cloned symbol object.
	 */
	function cloneSymbol(symbol) {
	  return symbolValueOf ? Object(symbolValueOf.call(symbol)) : {};
	}

	_cloneSymbol = cloneSymbol;
	return _cloneSymbol;
}

var _cloneTypedArray;
var hasRequired_cloneTypedArray;

function require_cloneTypedArray () {
	if (hasRequired_cloneTypedArray) return _cloneTypedArray;
	hasRequired_cloneTypedArray = 1;
	var cloneArrayBuffer = require_cloneArrayBuffer();

	/**
	 * Creates a clone of `typedArray`.
	 *
	 * @private
	 * @param {Object} typedArray The typed array to clone.
	 * @param {boolean} [isDeep] Specify a deep clone.
	 * @returns {Object} Returns the cloned typed array.
	 */
	function cloneTypedArray(typedArray, isDeep) {
	  var buffer = isDeep ? cloneArrayBuffer(typedArray.buffer) : typedArray.buffer;
	  return new typedArray.constructor(buffer, typedArray.byteOffset, typedArray.length);
	}

	_cloneTypedArray = cloneTypedArray;
	return _cloneTypedArray;
}

var _initCloneByTag;
var hasRequired_initCloneByTag;

function require_initCloneByTag () {
	if (hasRequired_initCloneByTag) return _initCloneByTag;
	hasRequired_initCloneByTag = 1;
	var cloneArrayBuffer = require_cloneArrayBuffer(),
	    cloneDataView = require_cloneDataView(),
	    cloneRegExp = require_cloneRegExp(),
	    cloneSymbol = require_cloneSymbol(),
	    cloneTypedArray = require_cloneTypedArray();

	/** `Object#toString` result references. */
	var boolTag = '[object Boolean]',
	    dateTag = '[object Date]',
	    mapTag = '[object Map]',
	    numberTag = '[object Number]',
	    regexpTag = '[object RegExp]',
	    setTag = '[object Set]',
	    stringTag = '[object String]',
	    symbolTag = '[object Symbol]';

	var arrayBufferTag = '[object ArrayBuffer]',
	    dataViewTag = '[object DataView]',
	    float32Tag = '[object Float32Array]',
	    float64Tag = '[object Float64Array]',
	    int8Tag = '[object Int8Array]',
	    int16Tag = '[object Int16Array]',
	    int32Tag = '[object Int32Array]',
	    uint8Tag = '[object Uint8Array]',
	    uint8ClampedTag = '[object Uint8ClampedArray]',
	    uint16Tag = '[object Uint16Array]',
	    uint32Tag = '[object Uint32Array]';

	/**
	 * Initializes an object clone based on its `toStringTag`.
	 *
	 * **Note:** This function only supports cloning values with tags of
	 * `Boolean`, `Date`, `Error`, `Map`, `Number`, `RegExp`, `Set`, or `String`.
	 *
	 * @private
	 * @param {Object} object The object to clone.
	 * @param {string} tag The `toStringTag` of the object to clone.
	 * @param {boolean} [isDeep] Specify a deep clone.
	 * @returns {Object} Returns the initialized clone.
	 */
	function initCloneByTag(object, tag, isDeep) {
	  var Ctor = object.constructor;
	  switch (tag) {
	    case arrayBufferTag:
	      return cloneArrayBuffer(object);

	    case boolTag:
	    case dateTag:
	      return new Ctor(+object);

	    case dataViewTag:
	      return cloneDataView(object, isDeep);

	    case float32Tag: case float64Tag:
	    case int8Tag: case int16Tag: case int32Tag:
	    case uint8Tag: case uint8ClampedTag: case uint16Tag: case uint32Tag:
	      return cloneTypedArray(object, isDeep);

	    case mapTag:
	      return new Ctor;

	    case numberTag:
	    case stringTag:
	      return new Ctor(object);

	    case regexpTag:
	      return cloneRegExp(object);

	    case setTag:
	      return new Ctor;

	    case symbolTag:
	      return cloneSymbol(object);
	  }
	}

	_initCloneByTag = initCloneByTag;
	return _initCloneByTag;
}

var _baseCreate;
var hasRequired_baseCreate;

function require_baseCreate () {
	if (hasRequired_baseCreate) return _baseCreate;
	hasRequired_baseCreate = 1;
	var isObject = requireIsObject();

	/** Built-in value references. */
	var objectCreate = Object.create;

	/**
	 * The base implementation of `_.create` without support for assigning
	 * properties to the created object.
	 *
	 * @private
	 * @param {Object} proto The object to inherit from.
	 * @returns {Object} Returns the new object.
	 */
	var baseCreate = (function() {
	  function object() {}
	  return function(proto) {
	    if (!isObject(proto)) {
	      return {};
	    }
	    if (objectCreate) {
	      return objectCreate(proto);
	    }
	    object.prototype = proto;
	    var result = new object;
	    object.prototype = undefined;
	    return result;
	  };
	}());

	_baseCreate = baseCreate;
	return _baseCreate;
}

var _initCloneObject;
var hasRequired_initCloneObject;

function require_initCloneObject () {
	if (hasRequired_initCloneObject) return _initCloneObject;
	hasRequired_initCloneObject = 1;
	var baseCreate = require_baseCreate(),
	    getPrototype = require_getPrototype(),
	    isPrototype = require_isPrototype();

	/**
	 * Initializes an object clone.
	 *
	 * @private
	 * @param {Object} object The object to clone.
	 * @returns {Object} Returns the initialized clone.
	 */
	function initCloneObject(object) {
	  return (typeof object.constructor == 'function' && !isPrototype(object))
	    ? baseCreate(getPrototype(object))
	    : {};
	}

	_initCloneObject = initCloneObject;
	return _initCloneObject;
}

var _baseIsMap;
var hasRequired_baseIsMap;

function require_baseIsMap () {
	if (hasRequired_baseIsMap) return _baseIsMap;
	hasRequired_baseIsMap = 1;
	var getTag = require_getTag(),
	    isObjectLike = requireIsObjectLike();

	/** `Object#toString` result references. */
	var mapTag = '[object Map]';

	/**
	 * The base implementation of `_.isMap` without Node.js optimizations.
	 *
	 * @private
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a map, else `false`.
	 */
	function baseIsMap(value) {
	  return isObjectLike(value) && getTag(value) == mapTag;
	}

	_baseIsMap = baseIsMap;
	return _baseIsMap;
}

var isMap_1;
var hasRequiredIsMap;

function requireIsMap () {
	if (hasRequiredIsMap) return isMap_1;
	hasRequiredIsMap = 1;
	var baseIsMap = require_baseIsMap(),
	    baseUnary = require_baseUnary(),
	    nodeUtil = require_nodeUtil();

	/* Node.js helper references. */
	var nodeIsMap = nodeUtil && nodeUtil.isMap;

	/**
	 * Checks if `value` is classified as a `Map` object.
	 *
	 * @static
	 * @memberOf _
	 * @since 4.3.0
	 * @category Lang
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a map, else `false`.
	 * @example
	 *
	 * _.isMap(new Map);
	 * // => true
	 *
	 * _.isMap(new WeakMap);
	 * // => false
	 */
	var isMap = nodeIsMap ? baseUnary(nodeIsMap) : baseIsMap;

	isMap_1 = isMap;
	return isMap_1;
}

var _baseIsSet;
var hasRequired_baseIsSet;

function require_baseIsSet () {
	if (hasRequired_baseIsSet) return _baseIsSet;
	hasRequired_baseIsSet = 1;
	var getTag = require_getTag(),
	    isObjectLike = requireIsObjectLike();

	/** `Object#toString` result references. */
	var setTag = '[object Set]';

	/**
	 * The base implementation of `_.isSet` without Node.js optimizations.
	 *
	 * @private
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a set, else `false`.
	 */
	function baseIsSet(value) {
	  return isObjectLike(value) && getTag(value) == setTag;
	}

	_baseIsSet = baseIsSet;
	return _baseIsSet;
}

var isSet_1;
var hasRequiredIsSet;

function requireIsSet () {
	if (hasRequiredIsSet) return isSet_1;
	hasRequiredIsSet = 1;
	var baseIsSet = require_baseIsSet(),
	    baseUnary = require_baseUnary(),
	    nodeUtil = require_nodeUtil();

	/* Node.js helper references. */
	var nodeIsSet = nodeUtil && nodeUtil.isSet;

	/**
	 * Checks if `value` is classified as a `Set` object.
	 *
	 * @static
	 * @memberOf _
	 * @since 4.3.0
	 * @category Lang
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a set, else `false`.
	 * @example
	 *
	 * _.isSet(new Set);
	 * // => true
	 *
	 * _.isSet(new WeakSet);
	 * // => false
	 */
	var isSet = nodeIsSet ? baseUnary(nodeIsSet) : baseIsSet;

	isSet_1 = isSet;
	return isSet_1;
}

var _baseClone;
var hasRequired_baseClone;

function require_baseClone () {
	if (hasRequired_baseClone) return _baseClone;
	hasRequired_baseClone = 1;
	var Stack = require_Stack(),
	    arrayEach = require_arrayEach(),
	    assignValue = require_assignValue(),
	    baseAssign = require_baseAssign(),
	    baseAssignIn = require_baseAssignIn(),
	    cloneBuffer = require_cloneBuffer(),
	    copyArray = require_copyArray(),
	    copySymbols = require_copySymbols(),
	    copySymbolsIn = require_copySymbolsIn(),
	    getAllKeys = require_getAllKeys(),
	    getAllKeysIn = require_getAllKeysIn(),
	    getTag = require_getTag(),
	    initCloneArray = require_initCloneArray(),
	    initCloneByTag = require_initCloneByTag(),
	    initCloneObject = require_initCloneObject(),
	    isArray = requireIsArray(),
	    isBuffer = requireIsBuffer(),
	    isMap = requireIsMap(),
	    isObject = requireIsObject(),
	    isSet = requireIsSet(),
	    keys = requireKeys(),
	    keysIn = requireKeysIn();

	/** Used to compose bitmasks for cloning. */
	var CLONE_DEEP_FLAG = 1,
	    CLONE_FLAT_FLAG = 2,
	    CLONE_SYMBOLS_FLAG = 4;

	/** `Object#toString` result references. */
	var argsTag = '[object Arguments]',
	    arrayTag = '[object Array]',
	    boolTag = '[object Boolean]',
	    dateTag = '[object Date]',
	    errorTag = '[object Error]',
	    funcTag = '[object Function]',
	    genTag = '[object GeneratorFunction]',
	    mapTag = '[object Map]',
	    numberTag = '[object Number]',
	    objectTag = '[object Object]',
	    regexpTag = '[object RegExp]',
	    setTag = '[object Set]',
	    stringTag = '[object String]',
	    symbolTag = '[object Symbol]',
	    weakMapTag = '[object WeakMap]';

	var arrayBufferTag = '[object ArrayBuffer]',
	    dataViewTag = '[object DataView]',
	    float32Tag = '[object Float32Array]',
	    float64Tag = '[object Float64Array]',
	    int8Tag = '[object Int8Array]',
	    int16Tag = '[object Int16Array]',
	    int32Tag = '[object Int32Array]',
	    uint8Tag = '[object Uint8Array]',
	    uint8ClampedTag = '[object Uint8ClampedArray]',
	    uint16Tag = '[object Uint16Array]',
	    uint32Tag = '[object Uint32Array]';

	/** Used to identify `toStringTag` values supported by `_.clone`. */
	var cloneableTags = {};
	cloneableTags[argsTag] = cloneableTags[arrayTag] =
	cloneableTags[arrayBufferTag] = cloneableTags[dataViewTag] =
	cloneableTags[boolTag] = cloneableTags[dateTag] =
	cloneableTags[float32Tag] = cloneableTags[float64Tag] =
	cloneableTags[int8Tag] = cloneableTags[int16Tag] =
	cloneableTags[int32Tag] = cloneableTags[mapTag] =
	cloneableTags[numberTag] = cloneableTags[objectTag] =
	cloneableTags[regexpTag] = cloneableTags[setTag] =
	cloneableTags[stringTag] = cloneableTags[symbolTag] =
	cloneableTags[uint8Tag] = cloneableTags[uint8ClampedTag] =
	cloneableTags[uint16Tag] = cloneableTags[uint32Tag] = true;
	cloneableTags[errorTag] = cloneableTags[funcTag] =
	cloneableTags[weakMapTag] = false;

	/**
	 * The base implementation of `_.clone` and `_.cloneDeep` which tracks
	 * traversed objects.
	 *
	 * @private
	 * @param {*} value The value to clone.
	 * @param {boolean} bitmask The bitmask flags.
	 *  1 - Deep clone
	 *  2 - Flatten inherited properties
	 *  4 - Clone symbols
	 * @param {Function} [customizer] The function to customize cloning.
	 * @param {string} [key] The key of `value`.
	 * @param {Object} [object] The parent object of `value`.
	 * @param {Object} [stack] Tracks traversed objects and their clone counterparts.
	 * @returns {*} Returns the cloned value.
	 */
	function baseClone(value, bitmask, customizer, key, object, stack) {
	  var result,
	      isDeep = bitmask & CLONE_DEEP_FLAG,
	      isFlat = bitmask & CLONE_FLAT_FLAG,
	      isFull = bitmask & CLONE_SYMBOLS_FLAG;

	  if (customizer) {
	    result = object ? customizer(value, key, object, stack) : customizer(value);
	  }
	  if (result !== undefined) {
	    return result;
	  }
	  if (!isObject(value)) {
	    return value;
	  }
	  var isArr = isArray(value);
	  if (isArr) {
	    result = initCloneArray(value);
	    if (!isDeep) {
	      return copyArray(value, result);
	    }
	  } else {
	    var tag = getTag(value),
	        isFunc = tag == funcTag || tag == genTag;

	    if (isBuffer(value)) {
	      return cloneBuffer(value, isDeep);
	    }
	    if (tag == objectTag || tag == argsTag || (isFunc && !object)) {
	      result = (isFlat || isFunc) ? {} : initCloneObject(value);
	      if (!isDeep) {
	        return isFlat
	          ? copySymbolsIn(value, baseAssignIn(result, value))
	          : copySymbols(value, baseAssign(result, value));
	      }
	    } else {
	      if (!cloneableTags[tag]) {
	        return object ? value : {};
	      }
	      result = initCloneByTag(value, tag, isDeep);
	    }
	  }
	  // Check for circular references and return its corresponding clone.
	  stack || (stack = new Stack);
	  var stacked = stack.get(value);
	  if (stacked) {
	    return stacked;
	  }
	  stack.set(value, result);

	  if (isSet(value)) {
	    value.forEach(function(subValue) {
	      result.add(baseClone(subValue, bitmask, customizer, subValue, value, stack));
	    });
	  } else if (isMap(value)) {
	    value.forEach(function(subValue, key) {
	      result.set(key, baseClone(subValue, bitmask, customizer, key, value, stack));
	    });
	  }

	  var keysFunc = isFull
	    ? (isFlat ? getAllKeysIn : getAllKeys)
	    : (isFlat ? keysIn : keys);

	  var props = isArr ? undefined : keysFunc(value);
	  arrayEach(props || value, function(subValue, key) {
	    if (props) {
	      key = subValue;
	      subValue = value[key];
	    }
	    // Recursively populate clone (susceptible to call stack limits).
	    assignValue(result, key, baseClone(subValue, bitmask, customizer, key, value, stack));
	  });
	  return result;
	}

	_baseClone = baseClone;
	return _baseClone;
}

var isSymbol_1;
var hasRequiredIsSymbol;

function requireIsSymbol () {
	if (hasRequiredIsSymbol) return isSymbol_1;
	hasRequiredIsSymbol = 1;
	var baseGetTag = require_baseGetTag(),
	    isObjectLike = requireIsObjectLike();

	/** `Object#toString` result references. */
	var symbolTag = '[object Symbol]';

	/**
	 * Checks if `value` is classified as a `Symbol` primitive or object.
	 *
	 * @static
	 * @memberOf _
	 * @since 4.0.0
	 * @category Lang
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a symbol, else `false`.
	 * @example
	 *
	 * _.isSymbol(Symbol.iterator);
	 * // => true
	 *
	 * _.isSymbol('abc');
	 * // => false
	 */
	function isSymbol(value) {
	  return typeof value == 'symbol' ||
	    (isObjectLike(value) && baseGetTag(value) == symbolTag);
	}

	isSymbol_1 = isSymbol;
	return isSymbol_1;
}

var _isKey;
var hasRequired_isKey;

function require_isKey () {
	if (hasRequired_isKey) return _isKey;
	hasRequired_isKey = 1;
	var isArray = requireIsArray(),
	    isSymbol = requireIsSymbol();

	/** Used to match property names within property paths. */
	var reIsDeepProp = /\.|\[(?:[^[\]]*|(["'])(?:(?!\1)[^\\]|\\.)*?\1)\]/,
	    reIsPlainProp = /^\w*$/;

	/**
	 * Checks if `value` is a property name and not a property path.
	 *
	 * @private
	 * @param {*} value The value to check.
	 * @param {Object} [object] The object to query keys on.
	 * @returns {boolean} Returns `true` if `value` is a property name, else `false`.
	 */
	function isKey(value, object) {
	  if (isArray(value)) {
	    return false;
	  }
	  var type = typeof value;
	  if (type == 'number' || type == 'symbol' || type == 'boolean' ||
	      value == null || isSymbol(value)) {
	    return true;
	  }
	  return reIsPlainProp.test(value) || !reIsDeepProp.test(value) ||
	    (object != null && value in Object(object));
	}

	_isKey = isKey;
	return _isKey;
}

var memoize_1;
var hasRequiredMemoize;

function requireMemoize () {
	if (hasRequiredMemoize) return memoize_1;
	hasRequiredMemoize = 1;
	var MapCache = require_MapCache();

	/** Error message constants. */
	var FUNC_ERROR_TEXT = 'Expected a function';

	/**
	 * Creates a function that memoizes the result of `func`. If `resolver` is
	 * provided, it determines the cache key for storing the result based on the
	 * arguments provided to the memoized function. By default, the first argument
	 * provided to the memoized function is used as the map cache key. The `func`
	 * is invoked with the `this` binding of the memoized function.
	 *
	 * **Note:** The cache is exposed as the `cache` property on the memoized
	 * function. Its creation may be customized by replacing the `_.memoize.Cache`
	 * constructor with one whose instances implement the
	 * [`Map`](http://ecma-international.org/ecma-262/7.0/#sec-properties-of-the-map-prototype-object)
	 * method interface of `clear`, `delete`, `get`, `has`, and `set`.
	 *
	 * @static
	 * @memberOf _
	 * @since 0.1.0
	 * @category Function
	 * @param {Function} func The function to have its output memoized.
	 * @param {Function} [resolver] The function to resolve the cache key.
	 * @returns {Function} Returns the new memoized function.
	 * @example
	 *
	 * var object = { 'a': 1, 'b': 2 };
	 * var other = { 'c': 3, 'd': 4 };
	 *
	 * var values = _.memoize(_.values);
	 * values(object);
	 * // => [1, 2]
	 *
	 * values(other);
	 * // => [3, 4]
	 *
	 * object.a = 2;
	 * values(object);
	 * // => [1, 2]
	 *
	 * // Modify the result cache.
	 * values.cache.set(object, ['a', 'b']);
	 * values(object);
	 * // => ['a', 'b']
	 *
	 * // Replace `_.memoize.Cache`.
	 * _.memoize.Cache = WeakMap;
	 */
	function memoize(func, resolver) {
	  if (typeof func != 'function' || (resolver != null && typeof resolver != 'function')) {
	    throw new TypeError(FUNC_ERROR_TEXT);
	  }
	  var memoized = function() {
	    var args = arguments,
	        key = resolver ? resolver.apply(this, args) : args[0],
	        cache = memoized.cache;

	    if (cache.has(key)) {
	      return cache.get(key);
	    }
	    var result = func.apply(this, args);
	    memoized.cache = cache.set(key, result) || cache;
	    return result;
	  };
	  memoized.cache = new (memoize.Cache || MapCache);
	  return memoized;
	}

	// Expose `MapCache`.
	memoize.Cache = MapCache;

	memoize_1 = memoize;
	return memoize_1;
}

var _memoizeCapped;
var hasRequired_memoizeCapped;

function require_memoizeCapped () {
	if (hasRequired_memoizeCapped) return _memoizeCapped;
	hasRequired_memoizeCapped = 1;
	var memoize = requireMemoize();

	/** Used as the maximum memoize cache size. */
	var MAX_MEMOIZE_SIZE = 500;

	/**
	 * A specialized version of `_.memoize` which clears the memoized function's
	 * cache when it exceeds `MAX_MEMOIZE_SIZE`.
	 *
	 * @private
	 * @param {Function} func The function to have its output memoized.
	 * @returns {Function} Returns the new memoized function.
	 */
	function memoizeCapped(func) {
	  var result = memoize(func, function(key) {
	    if (cache.size === MAX_MEMOIZE_SIZE) {
	      cache.clear();
	    }
	    return key;
	  });

	  var cache = result.cache;
	  return result;
	}

	_memoizeCapped = memoizeCapped;
	return _memoizeCapped;
}

var _stringToPath;
var hasRequired_stringToPath;

function require_stringToPath () {
	if (hasRequired_stringToPath) return _stringToPath;
	hasRequired_stringToPath = 1;
	var memoizeCapped = require_memoizeCapped();

	/** Used to match property names within property paths. */
	var rePropName = /[^.[\]]+|\[(?:(-?\d+(?:\.\d+)?)|(["'])((?:(?!\2)[^\\]|\\.)*?)\2)\]|(?=(?:\.|\[\])(?:\.|\[\]|$))/g;

	/** Used to match backslashes in property paths. */
	var reEscapeChar = /\\(\\)?/g;

	/**
	 * Converts `string` to a property path array.
	 *
	 * @private
	 * @param {string} string The string to convert.
	 * @returns {Array} Returns the property path array.
	 */
	var stringToPath = memoizeCapped(function(string) {
	  var result = [];
	  if (string.charCodeAt(0) === 46 /* . */) {
	    result.push('');
	  }
	  string.replace(rePropName, function(match, number, quote, subString) {
	    result.push(quote ? subString.replace(reEscapeChar, '$1') : (number || match));
	  });
	  return result;
	});

	_stringToPath = stringToPath;
	return _stringToPath;
}

var _baseToString;
var hasRequired_baseToString;

function require_baseToString () {
	if (hasRequired_baseToString) return _baseToString;
	hasRequired_baseToString = 1;
	var Symbol = require_Symbol(),
	    arrayMap = require_arrayMap(),
	    isArray = requireIsArray(),
	    isSymbol = requireIsSymbol();

	/** Used to convert symbols to primitives and strings. */
	var symbolProto = Symbol ? Symbol.prototype : undefined,
	    symbolToString = symbolProto ? symbolProto.toString : undefined;

	/**
	 * The base implementation of `_.toString` which doesn't convert nullish
	 * values to empty strings.
	 *
	 * @private
	 * @param {*} value The value to process.
	 * @returns {string} Returns the string.
	 */
	function baseToString(value) {
	  // Exit early for strings to avoid a performance hit in some environments.
	  if (typeof value == 'string') {
	    return value;
	  }
	  if (isArray(value)) {
	    // Recursively convert values (susceptible to call stack limits).
	    return arrayMap(value, baseToString) + '';
	  }
	  if (isSymbol(value)) {
	    return symbolToString ? symbolToString.call(value) : '';
	  }
	  var result = (value + '');
	  return (result == '0' && (1 / value) == -Infinity) ? '-0' : result;
	}

	_baseToString = baseToString;
	return _baseToString;
}

var toString_1;
var hasRequiredToString;

function requireToString () {
	if (hasRequiredToString) return toString_1;
	hasRequiredToString = 1;
	var baseToString = require_baseToString();

	/**
	 * Converts `value` to a string. An empty string is returned for `null`
	 * and `undefined` values. The sign of `-0` is preserved.
	 *
	 * @static
	 * @memberOf _
	 * @since 4.0.0
	 * @category Lang
	 * @param {*} value The value to convert.
	 * @returns {string} Returns the converted string.
	 * @example
	 *
	 * _.toString(null);
	 * // => ''
	 *
	 * _.toString(-0);
	 * // => '-0'
	 *
	 * _.toString([1, 2, 3]);
	 * // => '1,2,3'
	 */
	function toString(value) {
	  return value == null ? '' : baseToString(value);
	}

	toString_1 = toString;
	return toString_1;
}

var _castPath;
var hasRequired_castPath;

function require_castPath () {
	if (hasRequired_castPath) return _castPath;
	hasRequired_castPath = 1;
	var isArray = requireIsArray(),
	    isKey = require_isKey(),
	    stringToPath = require_stringToPath(),
	    toString = requireToString();

	/**
	 * Casts `value` to a path array if it's not one.
	 *
	 * @private
	 * @param {*} value The value to inspect.
	 * @param {Object} [object] The object to query keys on.
	 * @returns {Array} Returns the cast property path array.
	 */
	function castPath(value, object) {
	  if (isArray(value)) {
	    return value;
	  }
	  return isKey(value, object) ? [value] : stringToPath(toString(value));
	}

	_castPath = castPath;
	return _castPath;
}

/**
 * Gets the last element of `array`.
 *
 * @static
 * @memberOf _
 * @since 0.1.0
 * @category Array
 * @param {Array} array The array to query.
 * @returns {*} Returns the last element of `array`.
 * @example
 *
 * _.last([1, 2, 3]);
 * // => 3
 */

var last_1;
var hasRequiredLast;

function requireLast () {
	if (hasRequiredLast) return last_1;
	hasRequiredLast = 1;
	function last(array) {
	  var length = array == null ? 0 : array.length;
	  return length ? array[length - 1] : undefined;
	}

	last_1 = last;
	return last_1;
}

var _toKey;
var hasRequired_toKey;

function require_toKey () {
	if (hasRequired_toKey) return _toKey;
	hasRequired_toKey = 1;
	var isSymbol = requireIsSymbol();

	/**
	 * Converts `value` to a string key if it's not a string or symbol.
	 *
	 * @private
	 * @param {*} value The value to inspect.
	 * @returns {string|symbol} Returns the key.
	 */
	function toKey(value) {
	  if (typeof value == 'string' || isSymbol(value)) {
	    return value;
	  }
	  var result = (value + '');
	  return (result == '0' && (1 / value) == -Infinity) ? '-0' : result;
	}

	_toKey = toKey;
	return _toKey;
}

var _baseGet;
var hasRequired_baseGet;

function require_baseGet () {
	if (hasRequired_baseGet) return _baseGet;
	hasRequired_baseGet = 1;
	var castPath = require_castPath(),
	    toKey = require_toKey();

	/**
	 * The base implementation of `_.get` without support for default values.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @param {Array|string} path The path of the property to get.
	 * @returns {*} Returns the resolved value.
	 */
	function baseGet(object, path) {
	  path = castPath(path, object);

	  var index = 0,
	      length = path.length;

	  while (object != null && index < length) {
	    object = object[toKey(path[index++])];
	  }
	  return (index && index == length) ? object : undefined;
	}

	_baseGet = baseGet;
	return _baseGet;
}

/**
 * The base implementation of `_.slice` without an iteratee call guard.
 *
 * @private
 * @param {Array} array The array to slice.
 * @param {number} [start=0] The start position.
 * @param {number} [end=array.length] The end position.
 * @returns {Array} Returns the slice of `array`.
 */

var _baseSlice;
var hasRequired_baseSlice;

function require_baseSlice () {
	if (hasRequired_baseSlice) return _baseSlice;
	hasRequired_baseSlice = 1;
	function baseSlice(array, start, end) {
	  var index = -1,
	      length = array.length;

	  if (start < 0) {
	    start = -start > length ? 0 : (length + start);
	  }
	  end = end > length ? length : end;
	  if (end < 0) {
	    end += length;
	  }
	  length = start > end ? 0 : ((end - start) >>> 0);
	  start >>>= 0;

	  var result = Array(length);
	  while (++index < length) {
	    result[index] = array[index + start];
	  }
	  return result;
	}

	_baseSlice = baseSlice;
	return _baseSlice;
}

var _parent;
var hasRequired_parent;

function require_parent () {
	if (hasRequired_parent) return _parent;
	hasRequired_parent = 1;
	var baseGet = require_baseGet(),
	    baseSlice = require_baseSlice();

	/**
	 * Gets the parent value at `path` of `object`.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @param {Array} path The path to get the parent value of.
	 * @returns {*} Returns the parent value.
	 */
	function parent(object, path) {
	  return path.length < 2 ? object : baseGet(object, baseSlice(path, 0, -1));
	}

	_parent = parent;
	return _parent;
}

var _baseUnset;
var hasRequired_baseUnset;

function require_baseUnset () {
	if (hasRequired_baseUnset) return _baseUnset;
	hasRequired_baseUnset = 1;
	var castPath = require_castPath(),
	    last = requireLast(),
	    parent = require_parent(),
	    toKey = require_toKey();

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/**
	 * The base implementation of `_.unset`.
	 *
	 * @private
	 * @param {Object} object The object to modify.
	 * @param {Array|string} path The property path to unset.
	 * @returns {boolean} Returns `true` if the property is deleted, else `false`.
	 */
	function baseUnset(object, path) {
	  path = castPath(path, object);

	  // Prevent prototype pollution:
	  // https://github.com/lodash/lodash/security/advisories/GHSA-xxjr-mmjv-4gpg
	  // https://github.com/lodash/lodash/security/advisories/GHSA-f23m-r3pf-42rh
	  var index = -1,
	      length = path.length;

	  if (!length) {
	    return true;
	  }

	  while (++index < length) {
	    var key = toKey(path[index]);

	    // Always block "__proto__" anywhere in the path if it's not expected
	    if (key === '__proto__' && !hasOwnProperty.call(object, '__proto__')) {
	      return false;
	    }

	    // Block constructor/prototype as non-terminal traversal keys to prevent
	    // escaping the object graph into built-in constructors and prototypes.
	    if ((key === 'constructor' || key === 'prototype') && index < length - 1) {
	      return false;
	    }
	  }

	  var obj = parent(object, path);
	  return obj == null || delete obj[toKey(last(path))];
	}

	_baseUnset = baseUnset;
	return _baseUnset;
}

var isPlainObject_1;
var hasRequiredIsPlainObject;

function requireIsPlainObject () {
	if (hasRequiredIsPlainObject) return isPlainObject_1;
	hasRequiredIsPlainObject = 1;
	var baseGetTag = require_baseGetTag(),
	    getPrototype = require_getPrototype(),
	    isObjectLike = requireIsObjectLike();

	/** `Object#toString` result references. */
	var objectTag = '[object Object]';

	/** Used for built-in method references. */
	var funcProto = Function.prototype,
	    objectProto = Object.prototype;

	/** Used to resolve the decompiled source of functions. */
	var funcToString = funcProto.toString;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/** Used to infer the `Object` constructor. */
	var objectCtorString = funcToString.call(Object);

	/**
	 * Checks if `value` is a plain object, that is, an object created by the
	 * `Object` constructor or one with a `[[Prototype]]` of `null`.
	 *
	 * @static
	 * @memberOf _
	 * @since 0.8.0
	 * @category Lang
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is a plain object, else `false`.
	 * @example
	 *
	 * function Foo() {
	 *   this.a = 1;
	 * }
	 *
	 * _.isPlainObject(new Foo);
	 * // => false
	 *
	 * _.isPlainObject([1, 2, 3]);
	 * // => false
	 *
	 * _.isPlainObject({ 'x': 0, 'y': 0 });
	 * // => true
	 *
	 * _.isPlainObject(Object.create(null));
	 * // => true
	 */
	function isPlainObject(value) {
	  if (!isObjectLike(value) || baseGetTag(value) != objectTag) {
	    return false;
	  }
	  var proto = getPrototype(value);
	  if (proto === null) {
	    return true;
	  }
	  var Ctor = hasOwnProperty.call(proto, 'constructor') && proto.constructor;
	  return typeof Ctor == 'function' && Ctor instanceof Ctor &&
	    funcToString.call(Ctor) == objectCtorString;
	}

	isPlainObject_1 = isPlainObject;
	return isPlainObject_1;
}

var _customOmitClone;
var hasRequired_customOmitClone;

function require_customOmitClone () {
	if (hasRequired_customOmitClone) return _customOmitClone;
	hasRequired_customOmitClone = 1;
	var isPlainObject = requireIsPlainObject();

	/**
	 * Used by `_.omit` to customize its `_.cloneDeep` use to only clone plain
	 * objects.
	 *
	 * @private
	 * @param {*} value The value to inspect.
	 * @param {string} key The key of the property to inspect.
	 * @returns {*} Returns the uncloned value or `undefined` to defer cloning to `_.cloneDeep`.
	 */
	function customOmitClone(value) {
	  return isPlainObject(value) ? undefined : value;
	}

	_customOmitClone = customOmitClone;
	return _customOmitClone;
}

var _isFlattenable;
var hasRequired_isFlattenable;

function require_isFlattenable () {
	if (hasRequired_isFlattenable) return _isFlattenable;
	hasRequired_isFlattenable = 1;
	var Symbol = require_Symbol(),
	    isArguments = requireIsArguments(),
	    isArray = requireIsArray();

	/** Built-in value references. */
	var spreadableSymbol = Symbol ? Symbol.isConcatSpreadable : undefined;

	/**
	 * Checks if `value` is a flattenable `arguments` object or array.
	 *
	 * @private
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` is flattenable, else `false`.
	 */
	function isFlattenable(value) {
	  return isArray(value) || isArguments(value) ||
	    !!(spreadableSymbol && value && value[spreadableSymbol]);
	}

	_isFlattenable = isFlattenable;
	return _isFlattenable;
}

var _baseFlatten;
var hasRequired_baseFlatten;

function require_baseFlatten () {
	if (hasRequired_baseFlatten) return _baseFlatten;
	hasRequired_baseFlatten = 1;
	var arrayPush = require_arrayPush(),
	    isFlattenable = require_isFlattenable();

	/**
	 * The base implementation of `_.flatten` with support for restricting flattening.
	 *
	 * @private
	 * @param {Array} array The array to flatten.
	 * @param {number} depth The maximum recursion depth.
	 * @param {boolean} [predicate=isFlattenable] The function invoked per iteration.
	 * @param {boolean} [isStrict] Restrict to values that pass `predicate` checks.
	 * @param {Array} [result=[]] The initial result value.
	 * @returns {Array} Returns the new flattened array.
	 */
	function baseFlatten(array, depth, predicate, isStrict, result) {
	  var index = -1,
	      length = array.length;

	  predicate || (predicate = isFlattenable);
	  result || (result = []);

	  while (++index < length) {
	    var value = array[index];
	    if (depth > 0 && predicate(value)) {
	      if (depth > 1) {
	        // Recursively flatten arrays (susceptible to call stack limits).
	        baseFlatten(value, depth - 1, predicate, isStrict, result);
	      } else {
	        arrayPush(result, value);
	      }
	    } else if (!isStrict) {
	      result[result.length] = value;
	    }
	  }
	  return result;
	}

	_baseFlatten = baseFlatten;
	return _baseFlatten;
}

var flatten_1;
var hasRequiredFlatten;

function requireFlatten () {
	if (hasRequiredFlatten) return flatten_1;
	hasRequiredFlatten = 1;
	var baseFlatten = require_baseFlatten();

	/**
	 * Flattens `array` a single level deep.
	 *
	 * @static
	 * @memberOf _
	 * @since 0.1.0
	 * @category Array
	 * @param {Array} array The array to flatten.
	 * @returns {Array} Returns the new flattened array.
	 * @example
	 *
	 * _.flatten([1, [2, [3, [4]], 5]]);
	 * // => [1, 2, [3, [4]], 5]
	 */
	function flatten(array) {
	  var length = array == null ? 0 : array.length;
	  return length ? baseFlatten(array, 1) : [];
	}

	flatten_1 = flatten;
	return flatten_1;
}

/**
 * A faster alternative to `Function#apply`, this function invokes `func`
 * with the `this` binding of `thisArg` and the arguments of `args`.
 *
 * @private
 * @param {Function} func The function to invoke.
 * @param {*} thisArg The `this` binding of `func`.
 * @param {Array} args The arguments to invoke `func` with.
 * @returns {*} Returns the result of `func`.
 */

var _apply;
var hasRequired_apply;

function require_apply () {
	if (hasRequired_apply) return _apply;
	hasRequired_apply = 1;
	function apply(func, thisArg, args) {
	  switch (args.length) {
	    case 0: return func.call(thisArg);
	    case 1: return func.call(thisArg, args[0]);
	    case 2: return func.call(thisArg, args[0], args[1]);
	    case 3: return func.call(thisArg, args[0], args[1], args[2]);
	  }
	  return func.apply(thisArg, args);
	}

	_apply = apply;
	return _apply;
}

var _overRest;
var hasRequired_overRest;

function require_overRest () {
	if (hasRequired_overRest) return _overRest;
	hasRequired_overRest = 1;
	var apply = require_apply();

	/* Built-in method references for those with the same name as other `lodash` methods. */
	var nativeMax = Math.max;

	/**
	 * A specialized version of `baseRest` which transforms the rest array.
	 *
	 * @private
	 * @param {Function} func The function to apply a rest parameter to.
	 * @param {number} [start=func.length-1] The start position of the rest parameter.
	 * @param {Function} transform The rest array transform.
	 * @returns {Function} Returns the new function.
	 */
	function overRest(func, start, transform) {
	  start = nativeMax(start === undefined ? (func.length - 1) : start, 0);
	  return function() {
	    var args = arguments,
	        index = -1,
	        length = nativeMax(args.length - start, 0),
	        array = Array(length);

	    while (++index < length) {
	      array[index] = args[start + index];
	    }
	    index = -1;
	    var otherArgs = Array(start + 1);
	    while (++index < start) {
	      otherArgs[index] = args[index];
	    }
	    otherArgs[start] = transform(array);
	    return apply(func, this, otherArgs);
	  };
	}

	_overRest = overRest;
	return _overRest;
}

/**
 * Creates a function that returns `value`.
 *
 * @static
 * @memberOf _
 * @since 2.4.0
 * @category Util
 * @param {*} value The value to return from the new function.
 * @returns {Function} Returns the new constant function.
 * @example
 *
 * var objects = _.times(2, _.constant({ 'a': 1 }));
 *
 * console.log(objects);
 * // => [{ 'a': 1 }, { 'a': 1 }]
 *
 * console.log(objects[0] === objects[1]);
 * // => true
 */

var constant_1;
var hasRequiredConstant;

function requireConstant () {
	if (hasRequiredConstant) return constant_1;
	hasRequiredConstant = 1;
	function constant(value) {
	  return function() {
	    return value;
	  };
	}

	constant_1 = constant;
	return constant_1;
}

/**
 * This method returns the first argument it receives.
 *
 * @static
 * @since 0.1.0
 * @memberOf _
 * @category Util
 * @param {*} value Any value.
 * @returns {*} Returns `value`.
 * @example
 *
 * var object = { 'a': 1 };
 *
 * console.log(_.identity(object) === object);
 * // => true
 */

var identity_1;
var hasRequiredIdentity;

function requireIdentity () {
	if (hasRequiredIdentity) return identity_1;
	hasRequiredIdentity = 1;
	function identity(value) {
	  return value;
	}

	identity_1 = identity;
	return identity_1;
}

var _baseSetToString;
var hasRequired_baseSetToString;

function require_baseSetToString () {
	if (hasRequired_baseSetToString) return _baseSetToString;
	hasRequired_baseSetToString = 1;
	var constant = requireConstant(),
	    defineProperty = require_defineProperty(),
	    identity = requireIdentity();

	/**
	 * The base implementation of `setToString` without support for hot loop shorting.
	 *
	 * @private
	 * @param {Function} func The function to modify.
	 * @param {Function} string The `toString` result.
	 * @returns {Function} Returns `func`.
	 */
	var baseSetToString = !defineProperty ? identity : function(func, string) {
	  return defineProperty(func, 'toString', {
	    'configurable': true,
	    'enumerable': false,
	    'value': constant(string),
	    'writable': true
	  });
	};

	_baseSetToString = baseSetToString;
	return _baseSetToString;
}

/** Used to detect hot functions by number of calls within a span of milliseconds. */

var _shortOut;
var hasRequired_shortOut;

function require_shortOut () {
	if (hasRequired_shortOut) return _shortOut;
	hasRequired_shortOut = 1;
	var HOT_COUNT = 800,
	    HOT_SPAN = 16;

	/* Built-in method references for those with the same name as other `lodash` methods. */
	var nativeNow = Date.now;

	/**
	 * Creates a function that'll short out and invoke `identity` instead
	 * of `func` when it's called `HOT_COUNT` or more times in `HOT_SPAN`
	 * milliseconds.
	 *
	 * @private
	 * @param {Function} func The function to restrict.
	 * @returns {Function} Returns the new shortable function.
	 */
	function shortOut(func) {
	  var count = 0,
	      lastCalled = 0;

	  return function() {
	    var stamp = nativeNow(),
	        remaining = HOT_SPAN - (stamp - lastCalled);

	    lastCalled = stamp;
	    if (remaining > 0) {
	      if (++count >= HOT_COUNT) {
	        return arguments[0];
	      }
	    } else {
	      count = 0;
	    }
	    return func.apply(undefined, arguments);
	  };
	}

	_shortOut = shortOut;
	return _shortOut;
}

var _setToString;
var hasRequired_setToString;

function require_setToString () {
	if (hasRequired_setToString) return _setToString;
	hasRequired_setToString = 1;
	var baseSetToString = require_baseSetToString(),
	    shortOut = require_shortOut();

	/**
	 * Sets the `toString` method of `func` to return `string`.
	 *
	 * @private
	 * @param {Function} func The function to modify.
	 * @param {Function} string The `toString` result.
	 * @returns {Function} Returns `func`.
	 */
	var setToString = shortOut(baseSetToString);

	_setToString = setToString;
	return _setToString;
}

var _flatRest;
var hasRequired_flatRest;

function require_flatRest () {
	if (hasRequired_flatRest) return _flatRest;
	hasRequired_flatRest = 1;
	var flatten = requireFlatten(),
	    overRest = require_overRest(),
	    setToString = require_setToString();

	/**
	 * A specialized version of `baseRest` which flattens the rest array.
	 *
	 * @private
	 * @param {Function} func The function to apply a rest parameter to.
	 * @returns {Function} Returns the new function.
	 */
	function flatRest(func) {
	  return setToString(overRest(func, undefined, flatten), func + '');
	}

	_flatRest = flatRest;
	return _flatRest;
}

var omit_1;
var hasRequiredOmit;

function requireOmit () {
	if (hasRequiredOmit) return omit_1;
	hasRequiredOmit = 1;
	var arrayMap = require_arrayMap(),
	    baseClone = require_baseClone(),
	    baseUnset = require_baseUnset(),
	    castPath = require_castPath(),
	    copyObject = require_copyObject(),
	    customOmitClone = require_customOmitClone(),
	    flatRest = require_flatRest(),
	    getAllKeysIn = require_getAllKeysIn();

	/** Used to compose bitmasks for cloning. */
	var CLONE_DEEP_FLAG = 1,
	    CLONE_FLAT_FLAG = 2,
	    CLONE_SYMBOLS_FLAG = 4;

	/**
	 * The opposite of `_.pick`; this method creates an object composed of the
	 * own and inherited enumerable property paths of `object` that are not omitted.
	 *
	 * **Note:** This method is considerably slower than `_.pick`.
	 *
	 * @static
	 * @since 0.1.0
	 * @memberOf _
	 * @category Object
	 * @param {Object} object The source object.
	 * @param {...(string|string[])} [paths] The property paths to omit.
	 * @returns {Object} Returns the new object.
	 * @example
	 *
	 * var object = { 'a': 1, 'b': '2', 'c': 3 };
	 *
	 * _.omit(object, ['a', 'c']);
	 * // => { 'b': '2' }
	 */
	var omit = flatRest(function(object, paths) {
	  var result = {};
	  if (object == null) {
	    return result;
	  }
	  var isDeep = false;
	  paths = arrayMap(paths, function(path) {
	    path = castPath(path, object);
	    isDeep || (isDeep = path.length > 1);
	    return path;
	  });
	  copyObject(object, getAllKeysIn(object), result);
	  if (isDeep) {
	    result = baseClone(result, CLONE_DEEP_FLAG | CLONE_FLAT_FLAG | CLONE_SYMBOLS_FLAG, customOmitClone);
	  }
	  var length = paths.length;
	  while (length--) {
	    baseUnset(result, paths[length]);
	  }
	  return result;
	});

	omit_1 = omit;
	return omit_1;
}

var omitExports = requireOmit();
const omit = /*@__PURE__*/getDefaultExportFromCjs(omitExports);

/** Used to match a single whitespace character. */

var _trimmedEndIndex;
var hasRequired_trimmedEndIndex;

function require_trimmedEndIndex () {
	if (hasRequired_trimmedEndIndex) return _trimmedEndIndex;
	hasRequired_trimmedEndIndex = 1;
	var reWhitespace = /\s/;

	/**
	 * Used by `_.trim` and `_.trimEnd` to get the index of the last non-whitespace
	 * character of `string`.
	 *
	 * @private
	 * @param {string} string The string to inspect.
	 * @returns {number} Returns the index of the last non-whitespace character.
	 */
	function trimmedEndIndex(string) {
	  var index = string.length;

	  while (index-- && reWhitespace.test(string.charAt(index))) {}
	  return index;
	}

	_trimmedEndIndex = trimmedEndIndex;
	return _trimmedEndIndex;
}

var _baseTrim;
var hasRequired_baseTrim;

function require_baseTrim () {
	if (hasRequired_baseTrim) return _baseTrim;
	hasRequired_baseTrim = 1;
	var trimmedEndIndex = require_trimmedEndIndex();

	/** Used to match leading whitespace. */
	var reTrimStart = /^\s+/;

	/**
	 * The base implementation of `_.trim`.
	 *
	 * @private
	 * @param {string} string The string to trim.
	 * @returns {string} Returns the trimmed string.
	 */
	function baseTrim(string) {
	  return string
	    ? string.slice(0, trimmedEndIndex(string) + 1).replace(reTrimStart, '')
	    : string;
	}

	_baseTrim = baseTrim;
	return _baseTrim;
}

var toNumber_1;
var hasRequiredToNumber;

function requireToNumber () {
	if (hasRequiredToNumber) return toNumber_1;
	hasRequiredToNumber = 1;
	var baseTrim = require_baseTrim(),
	    isObject = requireIsObject(),
	    isSymbol = requireIsSymbol();

	/** Used as references for various `Number` constants. */
	var NAN = 0 / 0;

	/** Used to detect bad signed hexadecimal string values. */
	var reIsBadHex = /^[-+]0x[0-9a-f]+$/i;

	/** Used to detect binary string values. */
	var reIsBinary = /^0b[01]+$/i;

	/** Used to detect octal string values. */
	var reIsOctal = /^0o[0-7]+$/i;

	/** Built-in method references without a dependency on `root`. */
	var freeParseInt = parseInt;

	/**
	 * Converts `value` to a number.
	 *
	 * @static
	 * @memberOf _
	 * @since 4.0.0
	 * @category Lang
	 * @param {*} value The value to process.
	 * @returns {number} Returns the number.
	 * @example
	 *
	 * _.toNumber(3.2);
	 * // => 3.2
	 *
	 * _.toNumber(Number.MIN_VALUE);
	 * // => 5e-324
	 *
	 * _.toNumber(Infinity);
	 * // => Infinity
	 *
	 * _.toNumber('3.2');
	 * // => 3.2
	 */
	function toNumber(value) {
	  if (typeof value == 'number') {
	    return value;
	  }
	  if (isSymbol(value)) {
	    return NAN;
	  }
	  if (isObject(value)) {
	    var other = typeof value.valueOf == 'function' ? value.valueOf() : value;
	    value = isObject(other) ? (other + '') : other;
	  }
	  if (typeof value != 'string') {
	    return value === 0 ? value : +value;
	  }
	  value = baseTrim(value);
	  var isBinary = reIsBinary.test(value);
	  return (isBinary || reIsOctal.test(value))
	    ? freeParseInt(value.slice(2), isBinary ? 2 : 8)
	    : (reIsBadHex.test(value) ? NAN : +value);
	}

	toNumber_1 = toNumber;
	return toNumber_1;
}

var toFinite_1;
var hasRequiredToFinite;

function requireToFinite () {
	if (hasRequiredToFinite) return toFinite_1;
	hasRequiredToFinite = 1;
	var toNumber = requireToNumber();

	/** Used as references for various `Number` constants. */
	var INFINITY = 1 / 0,
	    MAX_INTEGER = 1.7976931348623157e+308;

	/**
	 * Converts `value` to a finite number.
	 *
	 * @static
	 * @memberOf _
	 * @since 4.12.0
	 * @category Lang
	 * @param {*} value The value to convert.
	 * @returns {number} Returns the converted number.
	 * @example
	 *
	 * _.toFinite(3.2);
	 * // => 3.2
	 *
	 * _.toFinite(Number.MIN_VALUE);
	 * // => 5e-324
	 *
	 * _.toFinite(Infinity);
	 * // => 1.7976931348623157e+308
	 *
	 * _.toFinite('3.2');
	 * // => 3.2
	 */
	function toFinite(value) {
	  if (!value) {
	    return value === 0 ? value : 0;
	  }
	  value = toNumber(value);
	  if (value === INFINITY || value === -INFINITY) {
	    var sign = (value < 0 ? -1 : 1);
	    return sign * MAX_INTEGER;
	  }
	  return value === value ? value : 0;
	}

	toFinite_1 = toFinite;
	return toFinite_1;
}

var toInteger_1;
var hasRequiredToInteger;

function requireToInteger () {
	if (hasRequiredToInteger) return toInteger_1;
	hasRequiredToInteger = 1;
	var toFinite = requireToFinite();

	/**
	 * Converts `value` to an integer.
	 *
	 * **Note:** This method is loosely based on
	 * [`ToInteger`](http://www.ecma-international.org/ecma-262/7.0/#sec-tointeger).
	 *
	 * @static
	 * @memberOf _
	 * @since 4.0.0
	 * @category Lang
	 * @param {*} value The value to convert.
	 * @returns {number} Returns the converted integer.
	 * @example
	 *
	 * _.toInteger(3.2);
	 * // => 3
	 *
	 * _.toInteger(Number.MIN_VALUE);
	 * // => 0
	 *
	 * _.toInteger(Infinity);
	 * // => 1.7976931348623157e+308
	 *
	 * _.toInteger('3.2');
	 * // => 3
	 */
	function toInteger(value) {
	  var result = toFinite(value),
	      remainder = result % 1;

	  return result === result ? (remainder ? result - remainder : result) : 0;
	}

	toInteger_1 = toInteger;
	return toInteger_1;
}

var _createRound;
var hasRequired_createRound;

function require_createRound () {
	if (hasRequired_createRound) return _createRound;
	hasRequired_createRound = 1;
	var root = require_root(),
	    toInteger = requireToInteger(),
	    toNumber = requireToNumber(),
	    toString = requireToString();

	/* Built-in method references for those with the same name as other `lodash` methods. */
	var nativeIsFinite = root.isFinite,
	    nativeMin = Math.min;

	/**
	 * Creates a function like `_.round`.
	 *
	 * @private
	 * @param {string} methodName The name of the `Math` method to use when rounding.
	 * @returns {Function} Returns the new round function.
	 */
	function createRound(methodName) {
	  var func = Math[methodName];
	  return function(number, precision) {
	    number = toNumber(number);
	    precision = precision == null ? 0 : nativeMin(toInteger(precision), 292);
	    if (precision && nativeIsFinite(number)) {
	      // Shift with exponential notation to avoid floating-point issues.
	      // See [MDN](https://mdn.io/round#Examples) for more details.
	      var pair = (toString(number) + 'e').split('e'),
	          value = func(pair[0] + 'e' + (+pair[1] + precision));

	      pair = (toString(value) + 'e').split('e');
	      return +(pair[0] + 'e' + (+pair[1] - precision));
	    }
	    return func(number);
	  };
	}

	_createRound = createRound;
	return _createRound;
}

var round_1;
var hasRequiredRound;

function requireRound () {
	if (hasRequiredRound) return round_1;
	hasRequiredRound = 1;
	var createRound = require_createRound();

	/**
	 * Computes `number` rounded to `precision`.
	 *
	 * @static
	 * @memberOf _
	 * @since 3.10.0
	 * @category Math
	 * @param {number} number The number to round.
	 * @param {number} [precision=0] The precision to round to.
	 * @returns {number} Returns the rounded number.
	 * @example
	 *
	 * _.round(4.006);
	 * // => 4
	 *
	 * _.round(4.006, 2);
	 * // => 4.01
	 *
	 * _.round(4060, -2);
	 * // => 4100
	 */
	var round = createRound('round');

	round_1 = round;
	return round_1;
}

var roundExports = requireRound();
const _round = /*@__PURE__*/getDefaultExportFromCjs(roundExports);

/** Used to stand-in for `undefined` hash values. */

var _setCacheAdd;
var hasRequired_setCacheAdd;

function require_setCacheAdd () {
	if (hasRequired_setCacheAdd) return _setCacheAdd;
	hasRequired_setCacheAdd = 1;
	var HASH_UNDEFINED = '__lodash_hash_undefined__';

	/**
	 * Adds `value` to the array cache.
	 *
	 * @private
	 * @name add
	 * @memberOf SetCache
	 * @alias push
	 * @param {*} value The value to cache.
	 * @returns {Object} Returns the cache instance.
	 */
	function setCacheAdd(value) {
	  this.__data__.set(value, HASH_UNDEFINED);
	  return this;
	}

	_setCacheAdd = setCacheAdd;
	return _setCacheAdd;
}

/**
 * Checks if `value` is in the array cache.
 *
 * @private
 * @name has
 * @memberOf SetCache
 * @param {*} value The value to search for.
 * @returns {boolean} Returns `true` if `value` is found, else `false`.
 */

var _setCacheHas;
var hasRequired_setCacheHas;

function require_setCacheHas () {
	if (hasRequired_setCacheHas) return _setCacheHas;
	hasRequired_setCacheHas = 1;
	function setCacheHas(value) {
	  return this.__data__.has(value);
	}

	_setCacheHas = setCacheHas;
	return _setCacheHas;
}

var _SetCache;
var hasRequired_SetCache;

function require_SetCache () {
	if (hasRequired_SetCache) return _SetCache;
	hasRequired_SetCache = 1;
	var MapCache = require_MapCache(),
	    setCacheAdd = require_setCacheAdd(),
	    setCacheHas = require_setCacheHas();

	/**
	 *
	 * Creates an array cache object to store unique values.
	 *
	 * @private
	 * @constructor
	 * @param {Array} [values] The values to cache.
	 */
	function SetCache(values) {
	  var index = -1,
	      length = values == null ? 0 : values.length;

	  this.__data__ = new MapCache;
	  while (++index < length) {
	    this.add(values[index]);
	  }
	}

	// Add methods to `SetCache`.
	SetCache.prototype.add = SetCache.prototype.push = setCacheAdd;
	SetCache.prototype.has = setCacheHas;

	_SetCache = SetCache;
	return _SetCache;
}

/**
 * A specialized version of `_.some` for arrays without support for iteratee
 * shorthands.
 *
 * @private
 * @param {Array} [array] The array to iterate over.
 * @param {Function} predicate The function invoked per iteration.
 * @returns {boolean} Returns `true` if any element passes the predicate check,
 *  else `false`.
 */

var _arraySome;
var hasRequired_arraySome;

function require_arraySome () {
	if (hasRequired_arraySome) return _arraySome;
	hasRequired_arraySome = 1;
	function arraySome(array, predicate) {
	  var index = -1,
	      length = array == null ? 0 : array.length;

	  while (++index < length) {
	    if (predicate(array[index], index, array)) {
	      return true;
	    }
	  }
	  return false;
	}

	_arraySome = arraySome;
	return _arraySome;
}

/**
 * Checks if a `cache` value for `key` exists.
 *
 * @private
 * @param {Object} cache The cache to query.
 * @param {string} key The key of the entry to check.
 * @returns {boolean} Returns `true` if an entry for `key` exists, else `false`.
 */

var _cacheHas;
var hasRequired_cacheHas;

function require_cacheHas () {
	if (hasRequired_cacheHas) return _cacheHas;
	hasRequired_cacheHas = 1;
	function cacheHas(cache, key) {
	  return cache.has(key);
	}

	_cacheHas = cacheHas;
	return _cacheHas;
}

var _equalArrays;
var hasRequired_equalArrays;

function require_equalArrays () {
	if (hasRequired_equalArrays) return _equalArrays;
	hasRequired_equalArrays = 1;
	var SetCache = require_SetCache(),
	    arraySome = require_arraySome(),
	    cacheHas = require_cacheHas();

	/** Used to compose bitmasks for value comparisons. */
	var COMPARE_PARTIAL_FLAG = 1,
	    COMPARE_UNORDERED_FLAG = 2;

	/**
	 * A specialized version of `baseIsEqualDeep` for arrays with support for
	 * partial deep comparisons.
	 *
	 * @private
	 * @param {Array} array The array to compare.
	 * @param {Array} other The other array to compare.
	 * @param {number} bitmask The bitmask flags. See `baseIsEqual` for more details.
	 * @param {Function} customizer The function to customize comparisons.
	 * @param {Function} equalFunc The function to determine equivalents of values.
	 * @param {Object} stack Tracks traversed `array` and `other` objects.
	 * @returns {boolean} Returns `true` if the arrays are equivalent, else `false`.
	 */
	function equalArrays(array, other, bitmask, customizer, equalFunc, stack) {
	  var isPartial = bitmask & COMPARE_PARTIAL_FLAG,
	      arrLength = array.length,
	      othLength = other.length;

	  if (arrLength != othLength && !(isPartial && othLength > arrLength)) {
	    return false;
	  }
	  // Check that cyclic values are equal.
	  var arrStacked = stack.get(array);
	  var othStacked = stack.get(other);
	  if (arrStacked && othStacked) {
	    return arrStacked == other && othStacked == array;
	  }
	  var index = -1,
	      result = true,
	      seen = (bitmask & COMPARE_UNORDERED_FLAG) ? new SetCache : undefined;

	  stack.set(array, other);
	  stack.set(other, array);

	  // Ignore non-index properties.
	  while (++index < arrLength) {
	    var arrValue = array[index],
	        othValue = other[index];

	    if (customizer) {
	      var compared = isPartial
	        ? customizer(othValue, arrValue, index, other, array, stack)
	        : customizer(arrValue, othValue, index, array, other, stack);
	    }
	    if (compared !== undefined) {
	      if (compared) {
	        continue;
	      }
	      result = false;
	      break;
	    }
	    // Recursively compare arrays (susceptible to call stack limits).
	    if (seen) {
	      if (!arraySome(other, function(othValue, othIndex) {
	            if (!cacheHas(seen, othIndex) &&
	                (arrValue === othValue || equalFunc(arrValue, othValue, bitmask, customizer, stack))) {
	              return seen.push(othIndex);
	            }
	          })) {
	        result = false;
	        break;
	      }
	    } else if (!(
	          arrValue === othValue ||
	            equalFunc(arrValue, othValue, bitmask, customizer, stack)
	        )) {
	      result = false;
	      break;
	    }
	  }
	  stack['delete'](array);
	  stack['delete'](other);
	  return result;
	}

	_equalArrays = equalArrays;
	return _equalArrays;
}

/**
 * Converts `map` to its key-value pairs.
 *
 * @private
 * @param {Object} map The map to convert.
 * @returns {Array} Returns the key-value pairs.
 */

var _mapToArray;
var hasRequired_mapToArray;

function require_mapToArray () {
	if (hasRequired_mapToArray) return _mapToArray;
	hasRequired_mapToArray = 1;
	function mapToArray(map) {
	  var index = -1,
	      result = Array(map.size);

	  map.forEach(function(value, key) {
	    result[++index] = [key, value];
	  });
	  return result;
	}

	_mapToArray = mapToArray;
	return _mapToArray;
}

/**
 * Converts `set` to an array of its values.
 *
 * @private
 * @param {Object} set The set to convert.
 * @returns {Array} Returns the values.
 */

var _setToArray;
var hasRequired_setToArray;

function require_setToArray () {
	if (hasRequired_setToArray) return _setToArray;
	hasRequired_setToArray = 1;
	function setToArray(set) {
	  var index = -1,
	      result = Array(set.size);

	  set.forEach(function(value) {
	    result[++index] = value;
	  });
	  return result;
	}

	_setToArray = setToArray;
	return _setToArray;
}

var _equalByTag;
var hasRequired_equalByTag;

function require_equalByTag () {
	if (hasRequired_equalByTag) return _equalByTag;
	hasRequired_equalByTag = 1;
	var Symbol = require_Symbol(),
	    Uint8Array = require_Uint8Array(),
	    eq = requireEq(),
	    equalArrays = require_equalArrays(),
	    mapToArray = require_mapToArray(),
	    setToArray = require_setToArray();

	/** Used to compose bitmasks for value comparisons. */
	var COMPARE_PARTIAL_FLAG = 1,
	    COMPARE_UNORDERED_FLAG = 2;

	/** `Object#toString` result references. */
	var boolTag = '[object Boolean]',
	    dateTag = '[object Date]',
	    errorTag = '[object Error]',
	    mapTag = '[object Map]',
	    numberTag = '[object Number]',
	    regexpTag = '[object RegExp]',
	    setTag = '[object Set]',
	    stringTag = '[object String]',
	    symbolTag = '[object Symbol]';

	var arrayBufferTag = '[object ArrayBuffer]',
	    dataViewTag = '[object DataView]';

	/** Used to convert symbols to primitives and strings. */
	var symbolProto = Symbol ? Symbol.prototype : undefined,
	    symbolValueOf = symbolProto ? symbolProto.valueOf : undefined;

	/**
	 * A specialized version of `baseIsEqualDeep` for comparing objects of
	 * the same `toStringTag`.
	 *
	 * **Note:** This function only supports comparing values with tags of
	 * `Boolean`, `Date`, `Error`, `Number`, `RegExp`, or `String`.
	 *
	 * @private
	 * @param {Object} object The object to compare.
	 * @param {Object} other The other object to compare.
	 * @param {string} tag The `toStringTag` of the objects to compare.
	 * @param {number} bitmask The bitmask flags. See `baseIsEqual` for more details.
	 * @param {Function} customizer The function to customize comparisons.
	 * @param {Function} equalFunc The function to determine equivalents of values.
	 * @param {Object} stack Tracks traversed `object` and `other` objects.
	 * @returns {boolean} Returns `true` if the objects are equivalent, else `false`.
	 */
	function equalByTag(object, other, tag, bitmask, customizer, equalFunc, stack) {
	  switch (tag) {
	    case dataViewTag:
	      if ((object.byteLength != other.byteLength) ||
	          (object.byteOffset != other.byteOffset)) {
	        return false;
	      }
	      object = object.buffer;
	      other = other.buffer;

	    case arrayBufferTag:
	      if ((object.byteLength != other.byteLength) ||
	          !equalFunc(new Uint8Array(object), new Uint8Array(other))) {
	        return false;
	      }
	      return true;

	    case boolTag:
	    case dateTag:
	    case numberTag:
	      // Coerce booleans to `1` or `0` and dates to milliseconds.
	      // Invalid dates are coerced to `NaN`.
	      return eq(+object, +other);

	    case errorTag:
	      return object.name == other.name && object.message == other.message;

	    case regexpTag:
	    case stringTag:
	      // Coerce regexes to strings and treat strings, primitives and objects,
	      // as equal. See http://www.ecma-international.org/ecma-262/7.0/#sec-regexp.prototype.tostring
	      // for more details.
	      return object == (other + '');

	    case mapTag:
	      var convert = mapToArray;

	    case setTag:
	      var isPartial = bitmask & COMPARE_PARTIAL_FLAG;
	      convert || (convert = setToArray);

	      if (object.size != other.size && !isPartial) {
	        return false;
	      }
	      // Assume cyclic values are equal.
	      var stacked = stack.get(object);
	      if (stacked) {
	        return stacked == other;
	      }
	      bitmask |= COMPARE_UNORDERED_FLAG;

	      // Recursively compare objects (susceptible to call stack limits).
	      stack.set(object, other);
	      var result = equalArrays(convert(object), convert(other), bitmask, customizer, equalFunc, stack);
	      stack['delete'](object);
	      return result;

	    case symbolTag:
	      if (symbolValueOf) {
	        return symbolValueOf.call(object) == symbolValueOf.call(other);
	      }
	  }
	  return false;
	}

	_equalByTag = equalByTag;
	return _equalByTag;
}

var _equalObjects;
var hasRequired_equalObjects;

function require_equalObjects () {
	if (hasRequired_equalObjects) return _equalObjects;
	hasRequired_equalObjects = 1;
	var getAllKeys = require_getAllKeys();

	/** Used to compose bitmasks for value comparisons. */
	var COMPARE_PARTIAL_FLAG = 1;

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/**
	 * A specialized version of `baseIsEqualDeep` for objects with support for
	 * partial deep comparisons.
	 *
	 * @private
	 * @param {Object} object The object to compare.
	 * @param {Object} other The other object to compare.
	 * @param {number} bitmask The bitmask flags. See `baseIsEqual` for more details.
	 * @param {Function} customizer The function to customize comparisons.
	 * @param {Function} equalFunc The function to determine equivalents of values.
	 * @param {Object} stack Tracks traversed `object` and `other` objects.
	 * @returns {boolean} Returns `true` if the objects are equivalent, else `false`.
	 */
	function equalObjects(object, other, bitmask, customizer, equalFunc, stack) {
	  var isPartial = bitmask & COMPARE_PARTIAL_FLAG,
	      objProps = getAllKeys(object),
	      objLength = objProps.length,
	      othProps = getAllKeys(other),
	      othLength = othProps.length;

	  if (objLength != othLength && !isPartial) {
	    return false;
	  }
	  var index = objLength;
	  while (index--) {
	    var key = objProps[index];
	    if (!(isPartial ? key in other : hasOwnProperty.call(other, key))) {
	      return false;
	    }
	  }
	  // Check that cyclic values are equal.
	  var objStacked = stack.get(object);
	  var othStacked = stack.get(other);
	  if (objStacked && othStacked) {
	    return objStacked == other && othStacked == object;
	  }
	  var result = true;
	  stack.set(object, other);
	  stack.set(other, object);

	  var skipCtor = isPartial;
	  while (++index < objLength) {
	    key = objProps[index];
	    var objValue = object[key],
	        othValue = other[key];

	    if (customizer) {
	      var compared = isPartial
	        ? customizer(othValue, objValue, key, other, object, stack)
	        : customizer(objValue, othValue, key, object, other, stack);
	    }
	    // Recursively compare objects (susceptible to call stack limits).
	    if (!(compared === undefined
	          ? (objValue === othValue || equalFunc(objValue, othValue, bitmask, customizer, stack))
	          : compared
	        )) {
	      result = false;
	      break;
	    }
	    skipCtor || (skipCtor = key == 'constructor');
	  }
	  if (result && !skipCtor) {
	    var objCtor = object.constructor,
	        othCtor = other.constructor;

	    // Non `Object` object instances with different constructors are not equal.
	    if (objCtor != othCtor &&
	        ('constructor' in object && 'constructor' in other) &&
	        !(typeof objCtor == 'function' && objCtor instanceof objCtor &&
	          typeof othCtor == 'function' && othCtor instanceof othCtor)) {
	      result = false;
	    }
	  }
	  stack['delete'](object);
	  stack['delete'](other);
	  return result;
	}

	_equalObjects = equalObjects;
	return _equalObjects;
}

var _baseIsEqualDeep;
var hasRequired_baseIsEqualDeep;

function require_baseIsEqualDeep () {
	if (hasRequired_baseIsEqualDeep) return _baseIsEqualDeep;
	hasRequired_baseIsEqualDeep = 1;
	var Stack = require_Stack(),
	    equalArrays = require_equalArrays(),
	    equalByTag = require_equalByTag(),
	    equalObjects = require_equalObjects(),
	    getTag = require_getTag(),
	    isArray = requireIsArray(),
	    isBuffer = requireIsBuffer(),
	    isTypedArray = requireIsTypedArray();

	/** Used to compose bitmasks for value comparisons. */
	var COMPARE_PARTIAL_FLAG = 1;

	/** `Object#toString` result references. */
	var argsTag = '[object Arguments]',
	    arrayTag = '[object Array]',
	    objectTag = '[object Object]';

	/** Used for built-in method references. */
	var objectProto = Object.prototype;

	/** Used to check objects for own properties. */
	var hasOwnProperty = objectProto.hasOwnProperty;

	/**
	 * A specialized version of `baseIsEqual` for arrays and objects which performs
	 * deep comparisons and tracks traversed objects enabling objects with circular
	 * references to be compared.
	 *
	 * @private
	 * @param {Object} object The object to compare.
	 * @param {Object} other The other object to compare.
	 * @param {number} bitmask The bitmask flags. See `baseIsEqual` for more details.
	 * @param {Function} customizer The function to customize comparisons.
	 * @param {Function} equalFunc The function to determine equivalents of values.
	 * @param {Object} [stack] Tracks traversed `object` and `other` objects.
	 * @returns {boolean} Returns `true` if the objects are equivalent, else `false`.
	 */
	function baseIsEqualDeep(object, other, bitmask, customizer, equalFunc, stack) {
	  var objIsArr = isArray(object),
	      othIsArr = isArray(other),
	      objTag = objIsArr ? arrayTag : getTag(object),
	      othTag = othIsArr ? arrayTag : getTag(other);

	  objTag = objTag == argsTag ? objectTag : objTag;
	  othTag = othTag == argsTag ? objectTag : othTag;

	  var objIsObj = objTag == objectTag,
	      othIsObj = othTag == objectTag,
	      isSameTag = objTag == othTag;

	  if (isSameTag && isBuffer(object)) {
	    if (!isBuffer(other)) {
	      return false;
	    }
	    objIsArr = true;
	    objIsObj = false;
	  }
	  if (isSameTag && !objIsObj) {
	    stack || (stack = new Stack);
	    return (objIsArr || isTypedArray(object))
	      ? equalArrays(object, other, bitmask, customizer, equalFunc, stack)
	      : equalByTag(object, other, objTag, bitmask, customizer, equalFunc, stack);
	  }
	  if (!(bitmask & COMPARE_PARTIAL_FLAG)) {
	    var objIsWrapped = objIsObj && hasOwnProperty.call(object, '__wrapped__'),
	        othIsWrapped = othIsObj && hasOwnProperty.call(other, '__wrapped__');

	    if (objIsWrapped || othIsWrapped) {
	      var objUnwrapped = objIsWrapped ? object.value() : object,
	          othUnwrapped = othIsWrapped ? other.value() : other;

	      stack || (stack = new Stack);
	      return equalFunc(objUnwrapped, othUnwrapped, bitmask, customizer, stack);
	    }
	  }
	  if (!isSameTag) {
	    return false;
	  }
	  stack || (stack = new Stack);
	  return equalObjects(object, other, bitmask, customizer, equalFunc, stack);
	}

	_baseIsEqualDeep = baseIsEqualDeep;
	return _baseIsEqualDeep;
}

var _baseIsEqual;
var hasRequired_baseIsEqual;

function require_baseIsEqual () {
	if (hasRequired_baseIsEqual) return _baseIsEqual;
	hasRequired_baseIsEqual = 1;
	var baseIsEqualDeep = require_baseIsEqualDeep(),
	    isObjectLike = requireIsObjectLike();

	/**
	 * The base implementation of `_.isEqual` which supports partial comparisons
	 * and tracks traversed objects.
	 *
	 * @private
	 * @param {*} value The value to compare.
	 * @param {*} other The other value to compare.
	 * @param {boolean} bitmask The bitmask flags.
	 *  1 - Unordered comparison
	 *  2 - Partial comparison
	 * @param {Function} [customizer] The function to customize comparisons.
	 * @param {Object} [stack] Tracks traversed `value` and `other` objects.
	 * @returns {boolean} Returns `true` if the values are equivalent, else `false`.
	 */
	function baseIsEqual(value, other, bitmask, customizer, stack) {
	  if (value === other) {
	    return true;
	  }
	  if (value == null || other == null || (!isObjectLike(value) && !isObjectLike(other))) {
	    return value !== value && other !== other;
	  }
	  return baseIsEqualDeep(value, other, bitmask, customizer, baseIsEqual, stack);
	}

	_baseIsEqual = baseIsEqual;
	return _baseIsEqual;
}

var _baseIsMatch;
var hasRequired_baseIsMatch;

function require_baseIsMatch () {
	if (hasRequired_baseIsMatch) return _baseIsMatch;
	hasRequired_baseIsMatch = 1;
	var Stack = require_Stack(),
	    baseIsEqual = require_baseIsEqual();

	/** Used to compose bitmasks for value comparisons. */
	var COMPARE_PARTIAL_FLAG = 1,
	    COMPARE_UNORDERED_FLAG = 2;

	/**
	 * The base implementation of `_.isMatch` without support for iteratee shorthands.
	 *
	 * @private
	 * @param {Object} object The object to inspect.
	 * @param {Object} source The object of property values to match.
	 * @param {Array} matchData The property names, values, and compare flags to match.
	 * @param {Function} [customizer] The function to customize comparisons.
	 * @returns {boolean} Returns `true` if `object` is a match, else `false`.
	 */
	function baseIsMatch(object, source, matchData, customizer) {
	  var index = matchData.length,
	      length = index,
	      noCustomizer = !customizer;

	  if (object == null) {
	    return !length;
	  }
	  object = Object(object);
	  while (index--) {
	    var data = matchData[index];
	    if ((noCustomizer && data[2])
	          ? data[1] !== object[data[0]]
	          : !(data[0] in object)
	        ) {
	      return false;
	    }
	  }
	  while (++index < length) {
	    data = matchData[index];
	    var key = data[0],
	        objValue = object[key],
	        srcValue = data[1];

	    if (noCustomizer && data[2]) {
	      if (objValue === undefined && !(key in object)) {
	        return false;
	      }
	    } else {
	      var stack = new Stack;
	      if (customizer) {
	        var result = customizer(objValue, srcValue, key, object, source, stack);
	      }
	      if (!(result === undefined
	            ? baseIsEqual(srcValue, objValue, COMPARE_PARTIAL_FLAG | COMPARE_UNORDERED_FLAG, customizer, stack)
	            : result
	          )) {
	        return false;
	      }
	    }
	  }
	  return true;
	}

	_baseIsMatch = baseIsMatch;
	return _baseIsMatch;
}

var _isStrictComparable;
var hasRequired_isStrictComparable;

function require_isStrictComparable () {
	if (hasRequired_isStrictComparable) return _isStrictComparable;
	hasRequired_isStrictComparable = 1;
	var isObject = requireIsObject();

	/**
	 * Checks if `value` is suitable for strict equality comparisons, i.e. `===`.
	 *
	 * @private
	 * @param {*} value The value to check.
	 * @returns {boolean} Returns `true` if `value` if suitable for strict
	 *  equality comparisons, else `false`.
	 */
	function isStrictComparable(value) {
	  return value === value && !isObject(value);
	}

	_isStrictComparable = isStrictComparable;
	return _isStrictComparable;
}

var _getMatchData;
var hasRequired_getMatchData;

function require_getMatchData () {
	if (hasRequired_getMatchData) return _getMatchData;
	hasRequired_getMatchData = 1;
	var isStrictComparable = require_isStrictComparable(),
	    keys = requireKeys();

	/**
	 * Gets the property names, values, and compare flags of `object`.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @returns {Array} Returns the match data of `object`.
	 */
	function getMatchData(object) {
	  var result = keys(object),
	      length = result.length;

	  while (length--) {
	    var key = result[length],
	        value = object[key];

	    result[length] = [key, value, isStrictComparable(value)];
	  }
	  return result;
	}

	_getMatchData = getMatchData;
	return _getMatchData;
}

/**
 * A specialized version of `matchesProperty` for source values suitable
 * for strict equality comparisons, i.e. `===`.
 *
 * @private
 * @param {string} key The key of the property to get.
 * @param {*} srcValue The value to match.
 * @returns {Function} Returns the new spec function.
 */

var _matchesStrictComparable;
var hasRequired_matchesStrictComparable;

function require_matchesStrictComparable () {
	if (hasRequired_matchesStrictComparable) return _matchesStrictComparable;
	hasRequired_matchesStrictComparable = 1;
	function matchesStrictComparable(key, srcValue) {
	  return function(object) {
	    if (object == null) {
	      return false;
	    }
	    return object[key] === srcValue &&
	      (srcValue !== undefined || (key in Object(object)));
	  };
	}

	_matchesStrictComparable = matchesStrictComparable;
	return _matchesStrictComparable;
}

var _baseMatches;
var hasRequired_baseMatches;

function require_baseMatches () {
	if (hasRequired_baseMatches) return _baseMatches;
	hasRequired_baseMatches = 1;
	var baseIsMatch = require_baseIsMatch(),
	    getMatchData = require_getMatchData(),
	    matchesStrictComparable = require_matchesStrictComparable();

	/**
	 * The base implementation of `_.matches` which doesn't clone `source`.
	 *
	 * @private
	 * @param {Object} source The object of property values to match.
	 * @returns {Function} Returns the new spec function.
	 */
	function baseMatches(source) {
	  var matchData = getMatchData(source);
	  if (matchData.length == 1 && matchData[0][2]) {
	    return matchesStrictComparable(matchData[0][0], matchData[0][1]);
	  }
	  return function(object) {
	    return object === source || baseIsMatch(object, source, matchData);
	  };
	}

	_baseMatches = baseMatches;
	return _baseMatches;
}

var get_1;
var hasRequiredGet;

function requireGet () {
	if (hasRequiredGet) return get_1;
	hasRequiredGet = 1;
	var baseGet = require_baseGet();

	/**
	 * Gets the value at `path` of `object`. If the resolved value is
	 * `undefined`, the `defaultValue` is returned in its place.
	 *
	 * @static
	 * @memberOf _
	 * @since 3.7.0
	 * @category Object
	 * @param {Object} object The object to query.
	 * @param {Array|string} path The path of the property to get.
	 * @param {*} [defaultValue] The value returned for `undefined` resolved values.
	 * @returns {*} Returns the resolved value.
	 * @example
	 *
	 * var object = { 'a': [{ 'b': { 'c': 3 } }] };
	 *
	 * _.get(object, 'a[0].b.c');
	 * // => 3
	 *
	 * _.get(object, ['a', '0', 'b', 'c']);
	 * // => 3
	 *
	 * _.get(object, 'a.b.c', 'default');
	 * // => 'default'
	 */
	function get(object, path, defaultValue) {
	  var result = object == null ? undefined : baseGet(object, path);
	  return result === undefined ? defaultValue : result;
	}

	get_1 = get;
	return get_1;
}

/**
 * The base implementation of `_.hasIn` without support for deep paths.
 *
 * @private
 * @param {Object} [object] The object to query.
 * @param {Array|string} key The key to check.
 * @returns {boolean} Returns `true` if `key` exists, else `false`.
 */

var _baseHasIn;
var hasRequired_baseHasIn;

function require_baseHasIn () {
	if (hasRequired_baseHasIn) return _baseHasIn;
	hasRequired_baseHasIn = 1;
	function baseHasIn(object, key) {
	  return object != null && key in Object(object);
	}

	_baseHasIn = baseHasIn;
	return _baseHasIn;
}

var _hasPath;
var hasRequired_hasPath;

function require_hasPath () {
	if (hasRequired_hasPath) return _hasPath;
	hasRequired_hasPath = 1;
	var castPath = require_castPath(),
	    isArguments = requireIsArguments(),
	    isArray = requireIsArray(),
	    isIndex = require_isIndex(),
	    isLength = requireIsLength(),
	    toKey = require_toKey();

	/**
	 * Checks if `path` exists on `object`.
	 *
	 * @private
	 * @param {Object} object The object to query.
	 * @param {Array|string} path The path to check.
	 * @param {Function} hasFunc The function to check properties.
	 * @returns {boolean} Returns `true` if `path` exists, else `false`.
	 */
	function hasPath(object, path, hasFunc) {
	  path = castPath(path, object);

	  var index = -1,
	      length = path.length,
	      result = false;

	  while (++index < length) {
	    var key = toKey(path[index]);
	    if (!(result = object != null && hasFunc(object, key))) {
	      break;
	    }
	    object = object[key];
	  }
	  if (result || ++index != length) {
	    return result;
	  }
	  length = object == null ? 0 : object.length;
	  return !!length && isLength(length) && isIndex(key, length) &&
	    (isArray(object) || isArguments(object));
	}

	_hasPath = hasPath;
	return _hasPath;
}

var hasIn_1;
var hasRequiredHasIn;

function requireHasIn () {
	if (hasRequiredHasIn) return hasIn_1;
	hasRequiredHasIn = 1;
	var baseHasIn = require_baseHasIn(),
	    hasPath = require_hasPath();

	/**
	 * Checks if `path` is a direct or inherited property of `object`.
	 *
	 * @static
	 * @memberOf _
	 * @since 4.0.0
	 * @category Object
	 * @param {Object} object The object to query.
	 * @param {Array|string} path The path to check.
	 * @returns {boolean} Returns `true` if `path` exists, else `false`.
	 * @example
	 *
	 * var object = _.create({ 'a': _.create({ 'b': 2 }) });
	 *
	 * _.hasIn(object, 'a');
	 * // => true
	 *
	 * _.hasIn(object, 'a.b');
	 * // => true
	 *
	 * _.hasIn(object, ['a', 'b']);
	 * // => true
	 *
	 * _.hasIn(object, 'b');
	 * // => false
	 */
	function hasIn(object, path) {
	  return object != null && hasPath(object, path, baseHasIn);
	}

	hasIn_1 = hasIn;
	return hasIn_1;
}

var _baseMatchesProperty;
var hasRequired_baseMatchesProperty;

function require_baseMatchesProperty () {
	if (hasRequired_baseMatchesProperty) return _baseMatchesProperty;
	hasRequired_baseMatchesProperty = 1;
	var baseIsEqual = require_baseIsEqual(),
	    get = requireGet(),
	    hasIn = requireHasIn(),
	    isKey = require_isKey(),
	    isStrictComparable = require_isStrictComparable(),
	    matchesStrictComparable = require_matchesStrictComparable(),
	    toKey = require_toKey();

	/** Used to compose bitmasks for value comparisons. */
	var COMPARE_PARTIAL_FLAG = 1,
	    COMPARE_UNORDERED_FLAG = 2;

	/**
	 * The base implementation of `_.matchesProperty` which doesn't clone `srcValue`.
	 *
	 * @private
	 * @param {string} path The path of the property to get.
	 * @param {*} srcValue The value to match.
	 * @returns {Function} Returns the new spec function.
	 */
	function baseMatchesProperty(path, srcValue) {
	  if (isKey(path) && isStrictComparable(srcValue)) {
	    return matchesStrictComparable(toKey(path), srcValue);
	  }
	  return function(object) {
	    var objValue = get(object, path);
	    return (objValue === undefined && objValue === srcValue)
	      ? hasIn(object, path)
	      : baseIsEqual(srcValue, objValue, COMPARE_PARTIAL_FLAG | COMPARE_UNORDERED_FLAG);
	  };
	}

	_baseMatchesProperty = baseMatchesProperty;
	return _baseMatchesProperty;
}

/**
 * The base implementation of `_.property` without support for deep paths.
 *
 * @private
 * @param {string} key The key of the property to get.
 * @returns {Function} Returns the new accessor function.
 */

var _baseProperty;
var hasRequired_baseProperty;

function require_baseProperty () {
	if (hasRequired_baseProperty) return _baseProperty;
	hasRequired_baseProperty = 1;
	function baseProperty(key) {
	  return function(object) {
	    return object == null ? undefined : object[key];
	  };
	}

	_baseProperty = baseProperty;
	return _baseProperty;
}

var _basePropertyDeep;
var hasRequired_basePropertyDeep;

function require_basePropertyDeep () {
	if (hasRequired_basePropertyDeep) return _basePropertyDeep;
	hasRequired_basePropertyDeep = 1;
	var baseGet = require_baseGet();

	/**
	 * A specialized version of `baseProperty` which supports deep paths.
	 *
	 * @private
	 * @param {Array|string} path The path of the property to get.
	 * @returns {Function} Returns the new accessor function.
	 */
	function basePropertyDeep(path) {
	  return function(object) {
	    return baseGet(object, path);
	  };
	}

	_basePropertyDeep = basePropertyDeep;
	return _basePropertyDeep;
}

var property_1;
var hasRequiredProperty;

function requireProperty () {
	if (hasRequiredProperty) return property_1;
	hasRequiredProperty = 1;
	var baseProperty = require_baseProperty(),
	    basePropertyDeep = require_basePropertyDeep(),
	    isKey = require_isKey(),
	    toKey = require_toKey();

	/**
	 * Creates a function that returns the value at `path` of a given object.
	 *
	 * @static
	 * @memberOf _
	 * @since 2.4.0
	 * @category Util
	 * @param {Array|string} path The path of the property to get.
	 * @returns {Function} Returns the new accessor function.
	 * @example
	 *
	 * var objects = [
	 *   { 'a': { 'b': 2 } },
	 *   { 'a': { 'b': 1 } }
	 * ];
	 *
	 * _.map(objects, _.property('a.b'));
	 * // => [2, 1]
	 *
	 * _.map(_.sortBy(objects, _.property(['a', 'b'])), 'a.b');
	 * // => [1, 2]
	 */
	function property(path) {
	  return isKey(path) ? baseProperty(toKey(path)) : basePropertyDeep(path);
	}

	property_1 = property;
	return property_1;
}

var _baseIteratee;
var hasRequired_baseIteratee;

function require_baseIteratee () {
	if (hasRequired_baseIteratee) return _baseIteratee;
	hasRequired_baseIteratee = 1;
	var baseMatches = require_baseMatches(),
	    baseMatchesProperty = require_baseMatchesProperty(),
	    identity = requireIdentity(),
	    isArray = requireIsArray(),
	    property = requireProperty();

	/**
	 * The base implementation of `_.iteratee`.
	 *
	 * @private
	 * @param {*} [value=_.identity] The value to convert to an iteratee.
	 * @returns {Function} Returns the iteratee.
	 */
	function baseIteratee(value) {
	  // Don't store the `typeof` result in a variable to avoid a JIT bug in Safari 9.
	  // See https://bugs.webkit.org/show_bug.cgi?id=156034 for more details.
	  if (typeof value == 'function') {
	    return value;
	  }
	  if (value == null) {
	    return identity;
	  }
	  if (typeof value == 'object') {
	    return isArray(value)
	      ? baseMatchesProperty(value[0], value[1])
	      : baseMatches(value);
	  }
	  return property(value);
	}

	_baseIteratee = baseIteratee;
	return _baseIteratee;
}

/**
 * Creates a base function for methods like `_.forIn` and `_.forOwn`.
 *
 * @private
 * @param {boolean} [fromRight] Specify iterating from right to left.
 * @returns {Function} Returns the new base function.
 */

var _createBaseFor;
var hasRequired_createBaseFor;

function require_createBaseFor () {
	if (hasRequired_createBaseFor) return _createBaseFor;
	hasRequired_createBaseFor = 1;
	function createBaseFor(fromRight) {
	  return function(object, iteratee, keysFunc) {
	    var index = -1,
	        iterable = Object(object),
	        props = keysFunc(object),
	        length = props.length;

	    while (length--) {
	      var key = props[fromRight ? length : ++index];
	      if (iteratee(iterable[key], key, iterable) === false) {
	        break;
	      }
	    }
	    return object;
	  };
	}

	_createBaseFor = createBaseFor;
	return _createBaseFor;
}

var _baseFor;
var hasRequired_baseFor;

function require_baseFor () {
	if (hasRequired_baseFor) return _baseFor;
	hasRequired_baseFor = 1;
	var createBaseFor = require_createBaseFor();

	/**
	 * The base implementation of `baseForOwn` which iterates over `object`
	 * properties returned by `keysFunc` and invokes `iteratee` for each property.
	 * Iteratee functions may exit iteration early by explicitly returning `false`.
	 *
	 * @private
	 * @param {Object} object The object to iterate over.
	 * @param {Function} iteratee The function invoked per iteration.
	 * @param {Function} keysFunc The function to get the keys of `object`.
	 * @returns {Object} Returns `object`.
	 */
	var baseFor = createBaseFor();

	_baseFor = baseFor;
	return _baseFor;
}

var _baseForOwn;
var hasRequired_baseForOwn;

function require_baseForOwn () {
	if (hasRequired_baseForOwn) return _baseForOwn;
	hasRequired_baseForOwn = 1;
	var baseFor = require_baseFor(),
	    keys = requireKeys();

	/**
	 * The base implementation of `_.forOwn` without support for iteratee shorthands.
	 *
	 * @private
	 * @param {Object} object The object to iterate over.
	 * @param {Function} iteratee The function invoked per iteration.
	 * @returns {Object} Returns `object`.
	 */
	function baseForOwn(object, iteratee) {
	  return object && baseFor(object, iteratee, keys);
	}

	_baseForOwn = baseForOwn;
	return _baseForOwn;
}

var _createBaseEach;
var hasRequired_createBaseEach;

function require_createBaseEach () {
	if (hasRequired_createBaseEach) return _createBaseEach;
	hasRequired_createBaseEach = 1;
	var isArrayLike = requireIsArrayLike();

	/**
	 * Creates a `baseEach` or `baseEachRight` function.
	 *
	 * @private
	 * @param {Function} eachFunc The function to iterate over a collection.
	 * @param {boolean} [fromRight] Specify iterating from right to left.
	 * @returns {Function} Returns the new base function.
	 */
	function createBaseEach(eachFunc, fromRight) {
	  return function(collection, iteratee) {
	    if (collection == null) {
	      return collection;
	    }
	    if (!isArrayLike(collection)) {
	      return eachFunc(collection, iteratee);
	    }
	    var length = collection.length,
	        index = fromRight ? length : -1,
	        iterable = Object(collection);

	    while ((fromRight ? index-- : ++index < length)) {
	      if (iteratee(iterable[index], index, iterable) === false) {
	        break;
	      }
	    }
	    return collection;
	  };
	}

	_createBaseEach = createBaseEach;
	return _createBaseEach;
}

var _baseEach;
var hasRequired_baseEach;

function require_baseEach () {
	if (hasRequired_baseEach) return _baseEach;
	hasRequired_baseEach = 1;
	var baseForOwn = require_baseForOwn(),
	    createBaseEach = require_createBaseEach();

	/**
	 * The base implementation of `_.forEach` without support for iteratee shorthands.
	 *
	 * @private
	 * @param {Array|Object} collection The collection to iterate over.
	 * @param {Function} iteratee The function invoked per iteration.
	 * @returns {Array|Object} Returns `collection`.
	 */
	var baseEach = createBaseEach(baseForOwn);

	_baseEach = baseEach;
	return _baseEach;
}

var _baseMap;
var hasRequired_baseMap;

function require_baseMap () {
	if (hasRequired_baseMap) return _baseMap;
	hasRequired_baseMap = 1;
	var baseEach = require_baseEach(),
	    isArrayLike = requireIsArrayLike();

	/**
	 * The base implementation of `_.map` without support for iteratee shorthands.
	 *
	 * @private
	 * @param {Array|Object} collection The collection to iterate over.
	 * @param {Function} iteratee The function invoked per iteration.
	 * @returns {Array} Returns the new mapped array.
	 */
	function baseMap(collection, iteratee) {
	  var index = -1,
	      result = isArrayLike(collection) ? Array(collection.length) : [];

	  baseEach(collection, function(value, key, collection) {
	    result[++index] = iteratee(value, key, collection);
	  });
	  return result;
	}

	_baseMap = baseMap;
	return _baseMap;
}

var map_1;
var hasRequiredMap;

function requireMap () {
	if (hasRequiredMap) return map_1;
	hasRequiredMap = 1;
	var arrayMap = require_arrayMap(),
	    baseIteratee = require_baseIteratee(),
	    baseMap = require_baseMap(),
	    isArray = requireIsArray();

	/**
	 * Creates an array of values by running each element in `collection` thru
	 * `iteratee`. The iteratee is invoked with three arguments:
	 * (value, index|key, collection).
	 *
	 * Many lodash methods are guarded to work as iteratees for methods like
	 * `_.every`, `_.filter`, `_.map`, `_.mapValues`, `_.reject`, and `_.some`.
	 *
	 * The guarded methods are:
	 * `ary`, `chunk`, `curry`, `curryRight`, `drop`, `dropRight`, `every`,
	 * `fill`, `invert`, `parseInt`, `random`, `range`, `rangeRight`, `repeat`,
	 * `sampleSize`, `slice`, `some`, `sortBy`, `split`, `take`, `takeRight`,
	 * `template`, `trim`, `trimEnd`, `trimStart`, and `words`
	 *
	 * @static
	 * @memberOf _
	 * @since 0.1.0
	 * @category Collection
	 * @param {Array|Object} collection The collection to iterate over.
	 * @param {Function} [iteratee=_.identity] The function invoked per iteration.
	 * @returns {Array} Returns the new mapped array.
	 * @example
	 *
	 * function square(n) {
	 *   return n * n;
	 * }
	 *
	 * _.map([4, 8], square);
	 * // => [16, 64]
	 *
	 * _.map({ 'a': 4, 'b': 8 }, square);
	 * // => [16, 64] (iteration order is not guaranteed)
	 *
	 * var users = [
	 *   { 'user': 'barney' },
	 *   { 'user': 'fred' }
	 * ];
	 *
	 * // The `_.property` iteratee shorthand.
	 * _.map(users, 'user');
	 * // => ['barney', 'fred']
	 */
	function map(collection, iteratee) {
	  var func = isArray(collection) ? arrayMap : baseMap;
	  return func(collection, baseIteratee(iteratee, 3));
	}

	map_1 = map;
	return map_1;
}

var mapExports = requireMap();
const _map = /*@__PURE__*/getDefaultExportFromCjs(mapExports);

var __defProp$1 = Object.defineProperty;
var __getOwnPropSymbols$1 = Object.getOwnPropertySymbols;
var __hasOwnProp$1 = Object.prototype.hasOwnProperty;
var __propIsEnum$1 = Object.prototype.propertyIsEnumerable;
var __defNormalProp$1 = (obj, key, value) => key in obj ? __defProp$1(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __spreadValues$1 = (a, b) => {
  for (var prop in b || (b = {}))
    if (__hasOwnProp$1.call(b, prop))
      __defNormalProp$1(a, prop, b[prop]);
  if (__getOwnPropSymbols$1)
    for (var prop of __getOwnPropSymbols$1(b)) {
      if (__propIsEnum$1.call(b, prop))
        __defNormalProp$1(a, prop, b[prop]);
    }
  return a;
};
var NOTHING = Symbol.for("immer-nothing");
var DRAFTABLE = Symbol.for("immer-draftable");
var DRAFT_STATE = Symbol.for("immer-state");
function die(error, ...args) {
  throw new Error(
    `[Immer] minified error nr: ${error}. Full error at: https://bit.ly/3cXEKWf`
  );
}
var getPrototypeOf = Object.getPrototypeOf;
function isDraft(value) {
  return !!value && !!value[DRAFT_STATE];
}
function isDraftable(value) {
  var _a;
  if (!value)
    return false;
  return isPlainObject(value) || Array.isArray(value) || !!value[DRAFTABLE] || !!((_a = value.constructor) == null ? void 0 : _a[DRAFTABLE]) || isMap(value) || isSet(value);
}
var objectCtorString = Object.prototype.constructor.toString();
function isPlainObject(value) {
  if (!value || typeof value !== "object")
    return false;
  const proto = getPrototypeOf(value);
  if (proto === null) {
    return true;
  }
  const Ctor = Object.hasOwnProperty.call(proto, "constructor") && proto.constructor;
  if (Ctor === Object)
    return true;
  return typeof Ctor == "function" && Function.toString.call(Ctor) === objectCtorString;
}
function each(obj, iter) {
  if (getArchtype(obj) === 0) {
    Reflect.ownKeys(obj).forEach((key) => {
      iter(key, obj[key], obj);
    });
  } else {
    obj.forEach((entry, index) => iter(index, entry, obj));
  }
}
function getArchtype(thing) {
  const state = thing[DRAFT_STATE];
  return state ? state.type_ : Array.isArray(thing) ? 1 : isMap(thing) ? 2 : isSet(thing) ? 3 : 0;
}
function has(thing, prop) {
  return getArchtype(thing) === 2 ? thing.has(prop) : Object.prototype.hasOwnProperty.call(thing, prop);
}
function set$2(thing, propOrOldValue, value) {
  const t = getArchtype(thing);
  if (t === 2)
    thing.set(propOrOldValue, value);
  else if (t === 3) {
    thing.add(value);
  } else
    thing[propOrOldValue] = value;
}
function is(x2, y2) {
  if (x2 === y2) {
    return x2 !== 0 || 1 / x2 === 1 / y2;
  } else {
    return x2 !== x2 && y2 !== y2;
  }
}
function isMap(target) {
  return target instanceof Map;
}
function isSet(target) {
  return target instanceof Set;
}
function latest(state) {
  return state.copy_ || state.base_;
}
function shallowCopy(base, strict) {
  if (isMap(base)) {
    return new Map(base);
  }
  if (isSet(base)) {
    return new Set(base);
  }
  if (Array.isArray(base))
    return Array.prototype.slice.call(base);
  const isPlain2 = isPlainObject(base);
  if (strict === true || strict === "class_only" && !isPlain2) {
    const descriptors = Object.getOwnPropertyDescriptors(base);
    delete descriptors[DRAFT_STATE];
    let keys = Reflect.ownKeys(descriptors);
    for (let i = 0; i < keys.length; i++) {
      const key = keys[i];
      const desc = descriptors[key];
      if (desc.writable === false) {
        desc.writable = true;
        desc.configurable = true;
      }
      if (desc.get || desc.set)
        descriptors[key] = {
          configurable: true,
          writable: true,
          // could live with !!desc.set as well here...
          enumerable: desc.enumerable,
          value: base[key]
        };
    }
    return Object.create(getPrototypeOf(base), descriptors);
  } else {
    const proto = getPrototypeOf(base);
    if (proto !== null && isPlain2) {
      return __spreadValues$1({}, base);
    }
    const obj = Object.create(proto);
    return Object.assign(obj, base);
  }
}
function freeze(obj, deep = false) {
  if (isFrozen(obj) || isDraft(obj) || !isDraftable(obj))
    return obj;
  if (getArchtype(obj) > 1) {
    obj.set = obj.add = obj.clear = obj.delete = dontMutateFrozenCollections;
  }
  Object.freeze(obj);
  if (deep)
    Object.entries(obj).forEach(([key, value]) => freeze(value, true));
  return obj;
}
function dontMutateFrozenCollections() {
  die(2);
}
function isFrozen(obj) {
  return Object.isFrozen(obj);
}
var plugins = {};
function getPlugin(pluginKey) {
  const plugin = plugins[pluginKey];
  if (!plugin) {
    die(0, pluginKey);
  }
  return plugin;
}
var currentScope;
function getCurrentScope() {
  return currentScope;
}
function createScope(parent_, immer_) {
  return {
    drafts_: [],
    parent_,
    immer_,
    // Whenever the modified draft contains a draft from another scope, we
    // need to prevent auto-freezing so the unowned draft can be finalized.
    canAutoFreeze_: true,
    unfinalizedDrafts_: 0
  };
}
function usePatchesInScope(scope, patchListener) {
  if (patchListener) {
    getPlugin("Patches");
    scope.patches_ = [];
    scope.inversePatches_ = [];
    scope.patchListener_ = patchListener;
  }
}
function revokeScope(scope) {
  leaveScope(scope);
  scope.drafts_.forEach(revokeDraft);
  scope.drafts_ = null;
}
function leaveScope(scope) {
  if (scope === currentScope) {
    currentScope = scope.parent_;
  }
}
function enterScope(immer2) {
  return currentScope = createScope(currentScope, immer2);
}
function revokeDraft(draft) {
  const state = draft[DRAFT_STATE];
  if (state.type_ === 0 || state.type_ === 1)
    state.revoke_();
  else
    state.revoked_ = true;
}
function processResult(result, scope) {
  scope.unfinalizedDrafts_ = scope.drafts_.length;
  const baseDraft = scope.drafts_[0];
  const isReplaced = result !== void 0 && result !== baseDraft;
  if (isReplaced) {
    if (baseDraft[DRAFT_STATE].modified_) {
      revokeScope(scope);
      die(4);
    }
    if (isDraftable(result)) {
      result = finalize(scope, result);
      if (!scope.parent_)
        maybeFreeze(scope, result);
    }
    if (scope.patches_) {
      getPlugin("Patches").generateReplacementPatches_(
        baseDraft[DRAFT_STATE].base_,
        result,
        scope.patches_,
        scope.inversePatches_
      );
    }
  } else {
    result = finalize(scope, baseDraft, []);
  }
  revokeScope(scope);
  if (scope.patches_) {
    scope.patchListener_(scope.patches_, scope.inversePatches_);
  }
  return result !== NOTHING ? result : void 0;
}
function finalize(rootScope, value, path) {
  if (isFrozen(value))
    return value;
  const state = value[DRAFT_STATE];
  if (!state) {
    each(
      value,
      (key, childValue) => finalizeProperty(rootScope, state, value, key, childValue, path)
    );
    return value;
  }
  if (state.scope_ !== rootScope)
    return value;
  if (!state.modified_) {
    maybeFreeze(rootScope, state.base_, true);
    return state.base_;
  }
  if (!state.finalized_) {
    state.finalized_ = true;
    state.scope_.unfinalizedDrafts_--;
    const result = state.copy_;
    let resultEach = result;
    let isSet2 = false;
    if (state.type_ === 3) {
      resultEach = new Set(result);
      result.clear();
      isSet2 = true;
    }
    each(
      resultEach,
      (key, childValue) => finalizeProperty(rootScope, state, result, key, childValue, path, isSet2)
    );
    maybeFreeze(rootScope, result, false);
    if (path && rootScope.patches_) {
      getPlugin("Patches").generatePatches_(
        state,
        path,
        rootScope.patches_,
        rootScope.inversePatches_
      );
    }
  }
  return state.copy_;
}
function finalizeProperty(rootScope, parentState, targetObject, prop, childValue, rootPath, targetIsSet) {
  if (isDraft(childValue)) {
    const path = rootPath && parentState && parentState.type_ !== 3 && // Set objects are atomic since they have no keys.
    !has(parentState.assigned_, prop) ? rootPath.concat(prop) : void 0;
    const res = finalize(rootScope, childValue, path);
    set$2(targetObject, prop, res);
    if (isDraft(res)) {
      rootScope.canAutoFreeze_ = false;
    } else
      return;
  } else if (targetIsSet) {
    targetObject.add(childValue);
  }
  if (isDraftable(childValue) && !isFrozen(childValue)) {
    if (!rootScope.immer_.autoFreeze_ && rootScope.unfinalizedDrafts_ < 1) {
      return;
    }
    finalize(rootScope, childValue);
    if ((!parentState || !parentState.scope_.parent_) && typeof prop !== "symbol" && Object.prototype.propertyIsEnumerable.call(targetObject, prop))
      maybeFreeze(rootScope, childValue);
  }
}
function maybeFreeze(scope, value, deep = false) {
  if (!scope.parent_ && scope.immer_.autoFreeze_ && scope.canAutoFreeze_) {
    freeze(value, deep);
  }
}
function createProxyProxy(base, parent) {
  const isArray = Array.isArray(base);
  const state = {
    type_: isArray ? 1 : 0,
    // Track which produce call this is associated with.
    scope_: parent ? parent.scope_ : getCurrentScope(),
    // True for both shallow and deep changes.
    modified_: false,
    // Used during finalization.
    finalized_: false,
    // Track which properties have been assigned (true) or deleted (false).
    assigned_: {},
    // The parent draft state.
    parent_: parent,
    // The base state.
    base_: base,
    // The base proxy.
    draft_: null,
    // set below
    // The base copy with any updated values.
    copy_: null,
    // Called by the `produce` function.
    revoke_: null,
    isManual_: false
  };
  let target = state;
  let traps = objectTraps;
  if (isArray) {
    target = [state];
    traps = arrayTraps;
  }
  const { revoke, proxy } = Proxy.revocable(target, traps);
  state.draft_ = proxy;
  state.revoke_ = revoke;
  return proxy;
}
var objectTraps = {
  get(state, prop) {
    if (prop === DRAFT_STATE)
      return state;
    const source = latest(state);
    if (!has(source, prop)) {
      return readPropFromProto(state, source, prop);
    }
    const value = source[prop];
    if (state.finalized_ || !isDraftable(value)) {
      return value;
    }
    if (value === peek(state.base_, prop)) {
      prepareCopy(state);
      return state.copy_[prop] = createProxy(value, state);
    }
    return value;
  },
  has(state, prop) {
    return prop in latest(state);
  },
  ownKeys(state) {
    return Reflect.ownKeys(latest(state));
  },
  set(state, prop, value) {
    const desc = getDescriptorFromProto(latest(state), prop);
    if (desc == null ? void 0 : desc.set) {
      desc.set.call(state.draft_, value);
      return true;
    }
    if (!state.modified_) {
      const current2 = peek(latest(state), prop);
      const currentState = current2 == null ? void 0 : current2[DRAFT_STATE];
      if (currentState && currentState.base_ === value) {
        state.copy_[prop] = value;
        state.assigned_[prop] = false;
        return true;
      }
      if (is(value, current2) && (value !== void 0 || has(state.base_, prop)))
        return true;
      prepareCopy(state);
      markChanged(state);
    }
    if (state.copy_[prop] === value && // special case: handle new props with value 'undefined'
    (value !== void 0 || prop in state.copy_) || // special case: NaN
    Number.isNaN(value) && Number.isNaN(state.copy_[prop]))
      return true;
    state.copy_[prop] = value;
    state.assigned_[prop] = true;
    return true;
  },
  deleteProperty(state, prop) {
    if (peek(state.base_, prop) !== void 0 || prop in state.base_) {
      state.assigned_[prop] = false;
      prepareCopy(state);
      markChanged(state);
    } else {
      delete state.assigned_[prop];
    }
    if (state.copy_) {
      delete state.copy_[prop];
    }
    return true;
  },
  // Note: We never coerce `desc.value` into an Immer draft, because we can't make
  // the same guarantee in ES5 mode.
  getOwnPropertyDescriptor(state, prop) {
    const owner = latest(state);
    const desc = Reflect.getOwnPropertyDescriptor(owner, prop);
    if (!desc)
      return desc;
    return {
      writable: true,
      configurable: state.type_ !== 1 || prop !== "length",
      enumerable: desc.enumerable,
      value: owner[prop]
    };
  },
  defineProperty() {
    die(11);
  },
  getPrototypeOf(state) {
    return getPrototypeOf(state.base_);
  },
  setPrototypeOf() {
    die(12);
  }
};
var arrayTraps = {};
each(objectTraps, (key, fn) => {
  arrayTraps[key] = function() {
    arguments[0] = arguments[0][0];
    return fn.apply(this, arguments);
  };
});
arrayTraps.deleteProperty = function(state, prop) {
  return arrayTraps.set.call(this, state, prop, void 0);
};
arrayTraps.set = function(state, prop, value) {
  return objectTraps.set.call(this, state[0], prop, value, state[0]);
};
function peek(draft, prop) {
  const state = draft[DRAFT_STATE];
  const source = state ? latest(state) : draft;
  return source[prop];
}
function readPropFromProto(state, source, prop) {
  var _a;
  const desc = getDescriptorFromProto(source, prop);
  return desc ? `value` in desc ? desc.value : (
    // This is a very special case, if the prop is a getter defined by the
    // prototype, we should invoke it with the draft as context!
    (_a = desc.get) == null ? void 0 : _a.call(state.draft_)
  ) : void 0;
}
function getDescriptorFromProto(source, prop) {
  if (!(prop in source))
    return void 0;
  let proto = getPrototypeOf(source);
  while (proto) {
    const desc = Object.getOwnPropertyDescriptor(proto, prop);
    if (desc)
      return desc;
    proto = getPrototypeOf(proto);
  }
  return void 0;
}
function markChanged(state) {
  if (!state.modified_) {
    state.modified_ = true;
    if (state.parent_) {
      markChanged(state.parent_);
    }
  }
}
function prepareCopy(state) {
  if (!state.copy_) {
    state.copy_ = shallowCopy(
      state.base_,
      state.scope_.immer_.useStrictShallowCopy_
    );
  }
}
var Immer2 = class {
  constructor(config) {
    this.autoFreeze_ = true;
    this.useStrictShallowCopy_ = false;
    this.produce = (base, recipe, patchListener) => {
      if (typeof base === "function" && typeof recipe !== "function") {
        const defaultBase = recipe;
        recipe = base;
        const self = this;
        return function curriedProduce(base2 = defaultBase, ...args) {
          return self.produce(base2, (draft) => recipe.call(this, draft, ...args));
        };
      }
      if (typeof recipe !== "function")
        die(6);
      if (patchListener !== void 0 && typeof patchListener !== "function")
        die(7);
      let result;
      if (isDraftable(base)) {
        const scope = enterScope(this);
        const proxy = createProxy(base, void 0);
        let hasError = true;
        try {
          result = recipe(proxy);
          hasError = false;
        } finally {
          if (hasError)
            revokeScope(scope);
          else
            leaveScope(scope);
        }
        usePatchesInScope(scope, patchListener);
        return processResult(result, scope);
      } else if (!base || typeof base !== "object") {
        result = recipe(base);
        if (result === void 0)
          result = base;
        if (result === NOTHING)
          result = void 0;
        if (this.autoFreeze_)
          freeze(result, true);
        if (patchListener) {
          const p = [];
          const ip = [];
          getPlugin("Patches").generateReplacementPatches_(base, result, p, ip);
          patchListener(p, ip);
        }
        return result;
      } else
        die(1, base);
    };
    this.produceWithPatches = (base, recipe) => {
      if (typeof base === "function") {
        return (state, ...args) => this.produceWithPatches(state, (draft) => base(draft, ...args));
      }
      let patches, inversePatches;
      const result = this.produce(base, recipe, (p, ip) => {
        patches = p;
        inversePatches = ip;
      });
      return [result, patches, inversePatches];
    };
    if (typeof (config == null ? void 0 : config.autoFreeze) === "boolean")
      this.setAutoFreeze(config.autoFreeze);
    if (typeof (config == null ? void 0 : config.useStrictShallowCopy) === "boolean")
      this.setUseStrictShallowCopy(config.useStrictShallowCopy);
  }
  createDraft(base) {
    if (!isDraftable(base))
      die(8);
    if (isDraft(base))
      base = current(base);
    const scope = enterScope(this);
    const proxy = createProxy(base, void 0);
    proxy[DRAFT_STATE].isManual_ = true;
    leaveScope(scope);
    return proxy;
  }
  finishDraft(draft, patchListener) {
    const state = draft && draft[DRAFT_STATE];
    if (!state || !state.isManual_)
      die(9);
    const { scope_: scope } = state;
    usePatchesInScope(scope, patchListener);
    return processResult(void 0, scope);
  }
  /**
   * Pass true to automatically freeze all copies created by Immer.
   *
   * By default, auto-freezing is enabled.
   */
  setAutoFreeze(value) {
    this.autoFreeze_ = value;
  }
  /**
   * Pass true to enable strict shallow copy.
   *
   * By default, immer does not copy the object descriptors such as getter, setter and non-enumrable properties.
   */
  setUseStrictShallowCopy(value) {
    this.useStrictShallowCopy_ = value;
  }
  applyPatches(base, patches) {
    let i;
    for (i = patches.length - 1; i >= 0; i--) {
      const patch = patches[i];
      if (patch.path.length === 0 && patch.op === "replace") {
        base = patch.value;
        break;
      }
    }
    if (i > -1) {
      patches = patches.slice(i + 1);
    }
    const applyPatchesImpl = getPlugin("Patches").applyPatches_;
    if (isDraft(base)) {
      return applyPatchesImpl(base, patches);
    }
    return this.produce(
      base,
      (draft) => applyPatchesImpl(draft, patches)
    );
  }
};
function createProxy(value, parent) {
  const draft = isMap(value) ? getPlugin("MapSet").proxyMap_(value, parent) : isSet(value) ? getPlugin("MapSet").proxySet_(value, parent) : createProxyProxy(value, parent);
  const scope = parent ? parent.scope_ : getCurrentScope();
  scope.drafts_.push(draft);
  return draft;
}
function current(value) {
  if (!isDraft(value))
    die(10, value);
  return currentImpl(value);
}
function currentImpl(value) {
  if (!isDraftable(value) || isFrozen(value))
    return value;
  const state = value[DRAFT_STATE];
  let copy2;
  if (state) {
    if (!state.modified_)
      return state.base_;
    state.finalized_ = true;
    copy2 = shallowCopy(value, state.scope_.immer_.useStrictShallowCopy_);
  } else {
    copy2 = shallowCopy(value, true);
  }
  each(copy2, (key, childValue) => {
    set$2(copy2, key, currentImpl(childValue));
  });
  if (state) {
    state.finalized_ = false;
  }
  return copy2;
}
var immer = new Immer2();
var produce = immer.produce;
immer.produceWithPatches.bind(
  immer
);
immer.setAutoFreeze.bind(immer);
immer.setUseStrictShallowCopy.bind(immer);
immer.applyPatches.bind(immer);
immer.createDraft.bind(immer);
immer.finishDraft.bind(immer);
var __defProp = Object.defineProperty;
var __defProps = Object.defineProperties;
var __getOwnPropDescs = Object.getOwnPropertyDescriptors;
var __getOwnPropSymbols = Object.getOwnPropertySymbols;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __propIsEnum = Object.prototype.propertyIsEnumerable;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __spreadValues = (a, b) => {
  for (var prop in b || (b = {}))
    if (__hasOwnProp.call(b, prop))
      __defNormalProp(a, prop, b[prop]);
  if (__getOwnPropSymbols)
    for (var prop of __getOwnPropSymbols(b)) {
      if (__propIsEnum.call(b, prop))
        __defNormalProp(a, prop, b[prop]);
    }
  return a;
};
var __spreadProps = (a, b) => __defProps(a, __getOwnPropDescs(b));
var __objRest = (source, exclude) => {
  var target = {};
  for (var prop in source)
    if (__hasOwnProp.call(source, prop) && exclude.indexOf(prop) < 0)
      target[prop] = source[prop];
  if (source != null && __getOwnPropSymbols)
    for (var prop of __getOwnPropSymbols(source)) {
      if (exclude.indexOf(prop) < 0 && __propIsEnum.call(source, prop))
        target[prop] = source[prop];
    }
  return target;
};
var composeWithDevTools = typeof window !== "undefined" && window.__REDUX_DEVTOOLS_EXTENSION_COMPOSE__ ? window.__REDUX_DEVTOOLS_EXTENSION_COMPOSE__ : function() {
  if (arguments.length === 0) return void 0;
  if (typeof arguments[0] === "object") return compose;
  return compose.apply(null, arguments);
};
function createAction(type, prepareAction) {
  function actionCreator(...args) {
    if (prepareAction) {
      let prepared = prepareAction(...args);
      if (!prepared) {
        throw new Error(formatProdErrorMessage(0) );
      }
      return __spreadValues(__spreadValues({
        type,
        payload: prepared.payload
      }, "meta" in prepared && {
        meta: prepared.meta
      }), "error" in prepared && {
        error: prepared.error
      });
    }
    return {
      type,
      payload: args[0]
    };
  }
  actionCreator.toString = () => `${type}`;
  actionCreator.type = type;
  actionCreator.match = (action) => isAction(action) && action.type === type;
  return actionCreator;
}
var Tuple = class _Tuple extends Array {
  constructor(...items) {
    super(...items);
    Object.setPrototypeOf(this, _Tuple.prototype);
  }
  static get [Symbol.species]() {
    return _Tuple;
  }
  concat(...arr) {
    return super.concat.apply(this, arr);
  }
  prepend(...arr) {
    if (arr.length === 1 && Array.isArray(arr[0])) {
      return new _Tuple(...arr[0].concat(this));
    }
    return new _Tuple(...arr.concat(this));
  }
};
function freezeDraftable(val) {
  return isDraftable(val) ? produce(val, () => {
  }) : val;
}
function getOrInsertComputed(map2, key, compute) {
  if (map2.has(key)) return map2.get(key);
  return map2.set(key, compute(key)).get(key);
}
function isBoolean(x2) {
  return typeof x2 === "boolean";
}
var buildGetDefaultMiddleware = () => function getDefaultMiddleware(options2) {
  const {
    thunk: thunk$1 = true,
    immutableCheck = true,
    serializableCheck = true,
    actionCreatorCheck = true
  } = options2 != null ? options2 : {};
  let middlewareArray = new Tuple();
  if (thunk$1) {
    if (isBoolean(thunk$1)) {
      middlewareArray.push(thunk);
    } else {
      middlewareArray.push(withExtraArgument(thunk$1.extraArgument));
    }
  }
  return middlewareArray;
};
var SHOULD_AUTOBATCH = "RTK_autoBatch";
var createQueueWithTimer = (timeout2) => {
  return (notify) => {
    setTimeout(notify, timeout2);
  };
};
var autoBatchEnhancer = (options2 = {
  type: "raf"
}) => (next) => (...args) => {
  const store2 = next(...args);
  let notifying = true;
  let shouldNotifyAtEndOfTick = false;
  let notificationQueued = false;
  const listeners = /* @__PURE__ */ new Set();
  const queueCallback = options2.type === "tick" ? queueMicrotask : options2.type === "raf" ? (
    // requestAnimationFrame won't exist in SSR environments. Fall back to a vague approximation just to keep from erroring.
    typeof window !== "undefined" && window.requestAnimationFrame ? window.requestAnimationFrame : createQueueWithTimer(10)
  ) : options2.type === "callback" ? options2.queueNotification : createQueueWithTimer(options2.timeout);
  const notifyListeners = () => {
    notificationQueued = false;
    if (shouldNotifyAtEndOfTick) {
      shouldNotifyAtEndOfTick = false;
      listeners.forEach((l) => l());
    }
  };
  return Object.assign({}, store2, {
    // Override the base `store.subscribe` method to keep original listeners
    // from running if we're delaying notifications
    subscribe(listener2) {
      const wrappedListener = () => notifying && listener2();
      const unsubscribe = store2.subscribe(wrappedListener);
      listeners.add(listener2);
      return () => {
        unsubscribe();
        listeners.delete(listener2);
      };
    },
    // Override the base `store.dispatch` method so that we can check actions
    // for the `shouldAutoBatch` flag and determine if batching is active
    dispatch(action) {
      var _a;
      try {
        notifying = !((_a = action == null ? void 0 : action.meta) == null ? void 0 : _a[SHOULD_AUTOBATCH]);
        shouldNotifyAtEndOfTick = !notifying;
        if (shouldNotifyAtEndOfTick) {
          if (!notificationQueued) {
            notificationQueued = true;
            queueCallback(notifyListeners);
          }
        }
        return store2.dispatch(action);
      } finally {
        notifying = true;
      }
    }
  });
};
var buildGetDefaultEnhancers = (middlewareEnhancer) => function getDefaultEnhancers(options2) {
  const {
    autoBatch = true
  } = options2 != null ? options2 : {};
  let enhancerArray = new Tuple(middlewareEnhancer);
  if (autoBatch) {
    enhancerArray.push(autoBatchEnhancer(typeof autoBatch === "object" ? autoBatch : void 0));
  }
  return enhancerArray;
};
function configureStore(options2) {
  const getDefaultMiddleware = buildGetDefaultMiddleware();
  const {
    reducer = void 0,
    middleware,
    devTools = true,
    preloadedState = void 0,
    enhancers = void 0
  } = options2 || {};
  let rootReducer;
  if (typeof reducer === "function") {
    rootReducer = reducer;
  } else if (isPlainObject$1(reducer)) {
    rootReducer = combineReducers(reducer);
  } else {
    throw new Error(formatProdErrorMessage(1) );
  }
  let finalMiddleware;
  if (typeof middleware === "function") {
    finalMiddleware = middleware(getDefaultMiddleware);
  } else {
    finalMiddleware = getDefaultMiddleware();
  }
  let finalCompose = compose;
  if (devTools) {
    finalCompose = composeWithDevTools(__spreadValues({
      // Enable capture of stack traces for dispatched Redux actions
      trace: false
    }, typeof devTools === "object" && devTools));
  }
  const middlewareEnhancer = applyMiddleware(...finalMiddleware);
  const getDefaultEnhancers = buildGetDefaultEnhancers(middlewareEnhancer);
  let storeEnhancers = typeof enhancers === "function" ? enhancers(getDefaultEnhancers) : getDefaultEnhancers();
  const composedEnhancer = finalCompose(...storeEnhancers);
  return createStore(rootReducer, preloadedState, composedEnhancer);
}
function executeReducerBuilderCallback(builderCallback) {
  const actionsMap = {};
  const actionMatchers = [];
  let defaultCaseReducer;
  const builder = {
    addCase(typeOrActionCreator, reducer) {
      const type = typeof typeOrActionCreator === "string" ? typeOrActionCreator : typeOrActionCreator.type;
      if (!type) {
        throw new Error(formatProdErrorMessage(28) );
      }
      if (type in actionsMap) {
        throw new Error(formatProdErrorMessage(29) );
      }
      actionsMap[type] = reducer;
      return builder;
    },
    addMatcher(matcher2, reducer) {
      actionMatchers.push({
        matcher: matcher2,
        reducer
      });
      return builder;
    },
    addDefaultCase(reducer) {
      defaultCaseReducer = reducer;
      return builder;
    }
  };
  builderCallback(builder);
  return [actionsMap, actionMatchers, defaultCaseReducer];
}
function isStateFunction(x2) {
  return typeof x2 === "function";
}
function createReducer(initialState2, mapOrBuilderCallback) {
  let [actionsMap, finalActionMatchers, finalDefaultCaseReducer] = executeReducerBuilderCallback(mapOrBuilderCallback);
  let getInitialState;
  if (isStateFunction(initialState2)) {
    getInitialState = () => freezeDraftable(initialState2());
  } else {
    const frozenInitialState = freezeDraftable(initialState2);
    getInitialState = () => frozenInitialState;
  }
  function reducer(state = getInitialState(), action) {
    let caseReducers = [actionsMap[action.type], ...finalActionMatchers.filter(({
      matcher: matcher2
    }) => matcher2(action)).map(({
      reducer: reducer2
    }) => reducer2)];
    if (caseReducers.filter((cr) => !!cr).length === 0) {
      caseReducers = [finalDefaultCaseReducer];
    }
    return caseReducers.reduce((previousState, caseReducer) => {
      if (caseReducer) {
        if (isDraft(previousState)) {
          const draft = previousState;
          const result = caseReducer(draft, action);
          if (result === void 0) {
            return previousState;
          }
          return result;
        } else if (!isDraftable(previousState)) {
          const result = caseReducer(previousState, action);
          if (result === void 0) {
            if (previousState === null) {
              return previousState;
            }
            throw Error("A case reducer on a non-draftable value must not return undefined");
          }
          return result;
        } else {
          return produce(previousState, (draft) => {
            return caseReducer(draft, action);
          });
        }
      }
      return previousState;
    }, state);
  }
  reducer.getInitialState = getInitialState;
  return reducer;
}
var asyncThunkSymbol = /* @__PURE__ */ Symbol.for("rtk-slice-createasyncthunk");
function getType(slice, actionKey) {
  return `${slice}/${actionKey}`;
}
function buildCreateSlice({
  creators
} = {}) {
  var _a;
  const cAT = (_a = creators == null ? void 0 : creators.asyncThunk) == null ? void 0 : _a[asyncThunkSymbol];
  return function createSlice2(options2) {
    const {
      name,
      reducerPath = name
    } = options2;
    if (!name) {
      throw new Error(formatProdErrorMessage(11) );
    }
    const reducers = (typeof options2.reducers === "function" ? options2.reducers(buildReducerCreators()) : options2.reducers) || {};
    const reducerNames = Object.keys(reducers);
    const context = {
      sliceCaseReducersByName: {},
      sliceCaseReducersByType: {},
      actionCreators: {},
      sliceMatchers: []
    };
    const contextMethods = {
      addCase(typeOrActionCreator, reducer2) {
        const type = typeof typeOrActionCreator === "string" ? typeOrActionCreator : typeOrActionCreator.type;
        if (!type) {
          throw new Error(formatProdErrorMessage(12) );
        }
        if (type in context.sliceCaseReducersByType) {
          throw new Error(formatProdErrorMessage(13) );
        }
        context.sliceCaseReducersByType[type] = reducer2;
        return contextMethods;
      },
      addMatcher(matcher2, reducer2) {
        context.sliceMatchers.push({
          matcher: matcher2,
          reducer: reducer2
        });
        return contextMethods;
      },
      exposeAction(name2, actionCreator) {
        context.actionCreators[name2] = actionCreator;
        return contextMethods;
      },
      exposeCaseReducer(name2, reducer2) {
        context.sliceCaseReducersByName[name2] = reducer2;
        return contextMethods;
      }
    };
    reducerNames.forEach((reducerName) => {
      const reducerDefinition = reducers[reducerName];
      const reducerDetails = {
        reducerName,
        type: getType(name, reducerName),
        createNotation: typeof options2.reducers === "function"
      };
      if (isAsyncThunkSliceReducerDefinition(reducerDefinition)) {
        handleThunkCaseReducerDefinition(reducerDetails, reducerDefinition, contextMethods, cAT);
      } else {
        handleNormalReducerDefinition(reducerDetails, reducerDefinition, contextMethods);
      }
    });
    function buildReducer() {
      const [extraReducers = {}, actionMatchers = [], defaultCaseReducer = void 0] = typeof options2.extraReducers === "function" ? executeReducerBuilderCallback(options2.extraReducers) : [options2.extraReducers];
      const finalCaseReducers = __spreadValues(__spreadValues({}, extraReducers), context.sliceCaseReducersByType);
      return createReducer(options2.initialState, (builder) => {
        for (let key in finalCaseReducers) {
          builder.addCase(key, finalCaseReducers[key]);
        }
        for (let sM of context.sliceMatchers) {
          builder.addMatcher(sM.matcher, sM.reducer);
        }
        for (let m of actionMatchers) {
          builder.addMatcher(m.matcher, m.reducer);
        }
        if (defaultCaseReducer) {
          builder.addDefaultCase(defaultCaseReducer);
        }
      });
    }
    const selectSelf = (state) => state;
    const injectedSelectorCache = /* @__PURE__ */ new Map();
    const injectedStateCache = /* @__PURE__ */ new WeakMap();
    let _reducer;
    function reducer(state, action) {
      if (!_reducer) _reducer = buildReducer();
      return _reducer(state, action);
    }
    function getInitialState() {
      if (!_reducer) _reducer = buildReducer();
      return _reducer.getInitialState();
    }
    function makeSelectorProps(reducerPath2, injected = false) {
      function selectSlice(state) {
        let sliceState = state[reducerPath2];
        if (typeof sliceState === "undefined") {
          if (injected) {
            sliceState = getOrInsertComputed(injectedStateCache, selectSlice, getInitialState);
          }
        }
        return sliceState;
      }
      function getSelectors(selectState = selectSelf) {
        const selectorCache = getOrInsertComputed(injectedSelectorCache, injected, () => /* @__PURE__ */ new WeakMap());
        return getOrInsertComputed(selectorCache, selectState, () => {
          var _a2;
          const map2 = {};
          for (const [name2, selector2] of Object.entries((_a2 = options2.selectors) != null ? _a2 : {})) {
            map2[name2] = wrapSelector(selector2, selectState, () => getOrInsertComputed(injectedStateCache, selectState, getInitialState), injected);
          }
          return map2;
        });
      }
      return {
        reducerPath: reducerPath2,
        getSelectors,
        get selectors() {
          return getSelectors(selectSlice);
        },
        selectSlice
      };
    }
    const slice = __spreadProps(__spreadValues({
      name,
      reducer,
      actions: context.actionCreators,
      caseReducers: context.sliceCaseReducersByName,
      getInitialState
    }, makeSelectorProps(reducerPath)), {
      injectInto(injectable, _a2 = {}) {
        var _b = _a2, {
          reducerPath: pathOpt
        } = _b, config = __objRest(_b, [
          "reducerPath"
        ]);
        const newReducerPath = pathOpt != null ? pathOpt : reducerPath;
        injectable.inject({
          reducerPath: newReducerPath,
          reducer
        }, config);
        return __spreadValues(__spreadValues({}, slice), makeSelectorProps(newReducerPath, true));
      }
    });
    return slice;
  };
}
function wrapSelector(selector2, selectState, getInitialState, injected) {
  function wrapper(rootState, ...args) {
    let sliceState = selectState(rootState);
    if (typeof sliceState === "undefined") {
      if (injected) {
        sliceState = getInitialState();
      }
    }
    return selector2(sliceState, ...args);
  }
  wrapper.unwrapped = selector2;
  return wrapper;
}
var createSlice = /* @__PURE__ */ buildCreateSlice();
function buildReducerCreators() {
  function asyncThunk(payloadCreator, config) {
    return __spreadValues({
      _reducerDefinitionType: "asyncThunk",
      payloadCreator
    }, config);
  }
  asyncThunk.withTypes = () => asyncThunk;
  return {
    reducer(caseReducer) {
      return Object.assign({
        // hack so the wrapping function has the same name as the original
        // we need to create a wrapper so the `reducerDefinitionType` is not assigned to the original
        [caseReducer.name](...args) {
          return caseReducer(...args);
        }
      }[caseReducer.name], {
        _reducerDefinitionType: "reducer"
        /* reducer */
      });
    },
    preparedReducer(prepare, reducer) {
      return {
        _reducerDefinitionType: "reducerWithPrepare",
        prepare,
        reducer
      };
    },
    asyncThunk
  };
}
function handleNormalReducerDefinition({
  type,
  reducerName,
  createNotation
}, maybeReducerWithPrepare, context) {
  let caseReducer;
  let prepareCallback;
  if ("reducer" in maybeReducerWithPrepare) {
    if (createNotation && !isCaseReducerWithPrepareDefinition(maybeReducerWithPrepare)) {
      throw new Error(formatProdErrorMessage(17) );
    }
    caseReducer = maybeReducerWithPrepare.reducer;
    prepareCallback = maybeReducerWithPrepare.prepare;
  } else {
    caseReducer = maybeReducerWithPrepare;
  }
  context.addCase(type, caseReducer).exposeCaseReducer(reducerName, caseReducer).exposeAction(reducerName, prepareCallback ? createAction(type, prepareCallback) : createAction(type));
}
function isAsyncThunkSliceReducerDefinition(reducerDefinition) {
  return reducerDefinition._reducerDefinitionType === "asyncThunk";
}
function isCaseReducerWithPrepareDefinition(reducerDefinition) {
  return reducerDefinition._reducerDefinitionType === "reducerWithPrepare";
}
function handleThunkCaseReducerDefinition({
  type,
  reducerName
}, reducerDefinition, context, cAT) {
  if (!cAT) {
    throw new Error(formatProdErrorMessage(18) );
  }
  const {
    payloadCreator,
    fulfilled,
    pending,
    rejected,
    settled,
    options: options2
  } = reducerDefinition;
  const thunk2 = cAT(type, payloadCreator, options2);
  context.exposeAction(reducerName, thunk2);
  if (fulfilled) {
    context.addCase(thunk2.fulfilled, fulfilled);
  }
  if (pending) {
    context.addCase(thunk2.pending, pending);
  }
  if (rejected) {
    context.addCase(thunk2.rejected, rejected);
  }
  if (settled) {
    context.addMatcher(thunk2.settled, settled);
  }
  context.exposeCaseReducer(reducerName, {
    fulfilled: fulfilled || noop$1,
    pending: pending || noop$1,
    rejected: rejected || noop$1,
    settled: settled || noop$1
  });
}
function noop$1() {
}
function formatProdErrorMessage(code) {
  return `Minified Redux Toolkit error #${code}; visit https://redux-toolkit.js.org/Errors?code=${code} for the full message or use the non-minified dev environment for full errors. `;
}
function ascending$1(a, b) {
  return a == null || b == null ? NaN : a < b ? -1 : a > b ? 1 : a >= b ? 0 : NaN;
}
function descending(a, b) {
  return a == null || b == null ? NaN : b < a ? -1 : b > a ? 1 : b >= a ? 0 : NaN;
}
function bisector(f) {
  let compare1, compare2, delta;
  if (f.length !== 2) {
    compare1 = ascending$1;
    compare2 = (d, x2) => ascending$1(f(d), x2);
    delta = (d, x2) => f(d) - x2;
  } else {
    compare1 = f === ascending$1 || f === descending ? f : zero$1;
    compare2 = f;
    delta = f;
  }
  function left2(a, x2, lo = 0, hi = a.length) {
    if (lo < hi) {
      if (compare1(x2, x2) !== 0) return hi;
      do {
        const mid = lo + hi >>> 1;
        if (compare2(a[mid], x2) < 0) lo = mid + 1;
        else hi = mid;
      } while (lo < hi);
    }
    return lo;
  }
  function right2(a, x2, lo = 0, hi = a.length) {
    if (lo < hi) {
      if (compare1(x2, x2) !== 0) return hi;
      do {
        const mid = lo + hi >>> 1;
        if (compare2(a[mid], x2) <= 0) lo = mid + 1;
        else hi = mid;
      } while (lo < hi);
    }
    return lo;
  }
  function center2(a, x2, lo = 0, hi = a.length) {
    const i = left2(a, x2, lo, hi - 1);
    return i > lo && delta(a[i - 1], x2) > -delta(a[i], x2) ? i - 1 : i;
  }
  return { left: left2, center: center2, right: right2 };
}
function zero$1() {
  return 0;
}
function number$2(x2) {
  return x2 === null ? NaN : +x2;
}
const ascendingBisect = bisector(ascending$1);
const bisectRight = ascendingBisect.right;
bisector(number$2).center;
var bisect = bisectRight;
const e10 = Math.sqrt(50), e5 = Math.sqrt(10), e2 = Math.sqrt(2);
function tickSpec(start2, stop, count) {
  const step = (stop - start2) / Math.max(0, count), power = Math.floor(Math.log10(step)), error = step / Math.pow(10, power), factor = error >= e10 ? 10 : error >= e5 ? 5 : error >= e2 ? 2 : 1;
  let i1, i2, inc;
  if (power < 0) {
    inc = Math.pow(10, -power) / factor;
    i1 = Math.round(start2 * inc);
    i2 = Math.round(stop * inc);
    if (i1 / inc < start2) ++i1;
    if (i2 / inc > stop) --i2;
    inc = -inc;
  } else {
    inc = Math.pow(10, power) * factor;
    i1 = Math.round(start2 / inc);
    i2 = Math.round(stop / inc);
    if (i1 * inc < start2) ++i1;
    if (i2 * inc > stop) --i2;
  }
  if (i2 < i1 && 0.5 <= count && count < 2) return tickSpec(start2, stop, count * 2);
  return [i1, i2, inc];
}
function ticks(start2, stop, count) {
  stop = +stop, start2 = +start2, count = +count;
  if (!(count > 0)) return [];
  if (start2 === stop) return [start2];
  const reverse = stop < start2, [i1, i2, inc] = reverse ? tickSpec(stop, start2, count) : tickSpec(start2, stop, count);
  if (!(i2 >= i1)) return [];
  const n = i2 - i1 + 1, ticks2 = new Array(n);
  if (reverse) {
    if (inc < 0) for (let i = 0; i < n; ++i) ticks2[i] = (i2 - i) / -inc;
    else for (let i = 0; i < n; ++i) ticks2[i] = (i2 - i) * inc;
  } else {
    if (inc < 0) for (let i = 0; i < n; ++i) ticks2[i] = (i1 + i) / -inc;
    else for (let i = 0; i < n; ++i) ticks2[i] = (i1 + i) * inc;
  }
  return ticks2;
}
function tickIncrement(start2, stop, count) {
  stop = +stop, start2 = +start2, count = +count;
  return tickSpec(start2, stop, count)[2];
}
function tickStep(start2, stop, count) {
  stop = +stop, start2 = +start2, count = +count;
  const reverse = stop < start2, inc = reverse ? tickIncrement(stop, start2, count) : tickIncrement(start2, stop, count);
  return (reverse ? -1 : 1) * (inc < 0 ? 1 / -inc : inc);
}
function identity$3(x2) {
  return x2;
}
var top = 1, right = 2, bottom = 3, left = 4, epsilon$1 = 1e-6;
function translateX(x2) {
  return "translate(" + x2 + ",0)";
}
function translateY(y2) {
  return "translate(0," + y2 + ")";
}
function number$1(scale) {
  return (d) => +scale(d);
}
function center(scale, offset) {
  offset = Math.max(0, scale.bandwidth() - offset * 2) / 2;
  if (scale.round()) offset = Math.round(offset);
  return (d) => +scale(d) + offset;
}
function entering() {
  return !this.__axis;
}
function axis(orient, scale) {
  var tickArguments = [], tickValues = null, tickFormat2 = null, tickSizeInner = 6, tickSizeOuter = 6, tickPadding = 3, offset = typeof window !== "undefined" && window.devicePixelRatio > 1 ? 0 : 0.5, k = orient === top || orient === left ? -1 : 1, x2 = orient === left || orient === right ? "x" : "y", transform = orient === top || orient === bottom ? translateX : translateY;
  function axis2(context) {
    var values = tickValues == null ? scale.ticks ? scale.ticks.apply(scale, tickArguments) : scale.domain() : tickValues, format2 = tickFormat2 == null ? scale.tickFormat ? scale.tickFormat.apply(scale, tickArguments) : identity$3 : tickFormat2, spacing = Math.max(tickSizeInner, 0) + tickPadding, range = scale.range(), range0 = +range[0] + offset, range1 = +range[range.length - 1] + offset, position = (scale.bandwidth ? center : number$1)(scale.copy(), offset), selection2 = context.selection ? context.selection() : context, path = selection2.selectAll(".domain").data([null]), tick = selection2.selectAll(".tick").data(values, scale).order(), tickExit = tick.exit(), tickEnter = tick.enter().append("g").attr("class", "tick"), line2 = tick.select("line"), text = tick.select("text");
    path = path.merge(path.enter().insert("path", ".tick").attr("class", "domain").attr("stroke", "currentColor"));
    tick = tick.merge(tickEnter);
    line2 = line2.merge(tickEnter.append("line").attr("stroke", "currentColor").attr(x2 + "2", k * tickSizeInner));
    text = text.merge(tickEnter.append("text").attr("fill", "currentColor").attr(x2, k * spacing).attr("dy", orient === top ? "0em" : orient === bottom ? "0.71em" : "0.32em"));
    if (context !== selection2) {
      path = path.transition(context);
      tick = tick.transition(context);
      line2 = line2.transition(context);
      text = text.transition(context);
      tickExit = tickExit.transition(context).attr("opacity", epsilon$1).attr("transform", function(d) {
        return isFinite(d = position(d)) ? transform(d + offset) : this.getAttribute("transform");
      });
      tickEnter.attr("opacity", epsilon$1).attr("transform", function(d) {
        var p = this.parentNode.__axis;
        return transform((p && isFinite(p = p(d)) ? p : position(d)) + offset);
      });
    }
    tickExit.remove();
    path.attr("d", orient === left || orient === right ? tickSizeOuter ? "M" + k * tickSizeOuter + "," + range0 + "H" + offset + "V" + range1 + "H" + k * tickSizeOuter : "M" + offset + "," + range0 + "V" + range1 : tickSizeOuter ? "M" + range0 + "," + k * tickSizeOuter + "V" + offset + "H" + range1 + "V" + k * tickSizeOuter : "M" + range0 + "," + offset + "H" + range1);
    tick.attr("opacity", 1).attr("transform", function(d) {
      return transform(position(d) + offset);
    });
    line2.attr(x2 + "2", k * tickSizeInner);
    text.attr(x2, k * spacing).text(format2);
    selection2.filter(entering).attr("fill", "none").attr("font-size", 10).attr("font-family", "sans-serif").attr("text-anchor", orient === right ? "start" : orient === left ? "end" : "middle");
    selection2.each(function() {
      this.__axis = position;
    });
  }
  axis2.scale = function(_2) {
    return arguments.length ? (scale = _2, axis2) : scale;
  };
  axis2.ticks = function() {
    return tickArguments = Array.from(arguments), axis2;
  };
  axis2.tickArguments = function(_2) {
    return arguments.length ? (tickArguments = _2 == null ? [] : Array.from(_2), axis2) : tickArguments.slice();
  };
  axis2.tickValues = function(_2) {
    return arguments.length ? (tickValues = _2 == null ? null : Array.from(_2), axis2) : tickValues && tickValues.slice();
  };
  axis2.tickFormat = function(_2) {
    return arguments.length ? (tickFormat2 = _2, axis2) : tickFormat2;
  };
  axis2.tickSize = function(_2) {
    return arguments.length ? (tickSizeInner = tickSizeOuter = +_2, axis2) : tickSizeInner;
  };
  axis2.tickSizeInner = function(_2) {
    return arguments.length ? (tickSizeInner = +_2, axis2) : tickSizeInner;
  };
  axis2.tickSizeOuter = function(_2) {
    return arguments.length ? (tickSizeOuter = +_2, axis2) : tickSizeOuter;
  };
  axis2.tickPadding = function(_2) {
    return arguments.length ? (tickPadding = +_2, axis2) : tickPadding;
  };
  axis2.offset = function(_2) {
    return arguments.length ? (offset = +_2, axis2) : offset;
  };
  return axis2;
}
function axisBottom(scale) {
  return axis(bottom, scale);
}
function axisLeft(scale) {
  return axis(left, scale);
}
var noop = { value: () => {
} };
function dispatch() {
  for (var i = 0, n = arguments.length, _2 = {}, t; i < n; ++i) {
    if (!(t = arguments[i] + "") || t in _2 || /[\s.]/.test(t)) throw new Error("illegal type: " + t);
    _2[t] = [];
  }
  return new Dispatch(_2);
}
function Dispatch(_2) {
  this._ = _2;
}
function parseTypenames$1(typenames, types) {
  return typenames.trim().split(/^|\s+/).map(function(t) {
    var name = "", i = t.indexOf(".");
    if (i >= 0) name = t.slice(i + 1), t = t.slice(0, i);
    if (t && !types.hasOwnProperty(t)) throw new Error("unknown type: " + t);
    return { type: t, name };
  });
}
Dispatch.prototype = dispatch.prototype = {
  constructor: Dispatch,
  on: function(typename, callback) {
    var _2 = this._, T = parseTypenames$1(typename + "", _2), t, i = -1, n = T.length;
    if (arguments.length < 2) {
      while (++i < n) if ((t = (typename = T[i]).type) && (t = get$1(_2[t], typename.name))) return t;
      return;
    }
    if (callback != null && typeof callback !== "function") throw new Error("invalid callback: " + callback);
    while (++i < n) {
      if (t = (typename = T[i]).type) _2[t] = set$1(_2[t], typename.name, callback);
      else if (callback == null) for (t in _2) _2[t] = set$1(_2[t], typename.name, null);
    }
    return this;
  },
  copy: function() {
    var copy2 = {}, _2 = this._;
    for (var t in _2) copy2[t] = _2[t].slice();
    return new Dispatch(copy2);
  },
  call: function(type, that) {
    if ((n = arguments.length - 2) > 0) for (var args = new Array(n), i = 0, n, t; i < n; ++i) args[i] = arguments[i + 2];
    if (!this._.hasOwnProperty(type)) throw new Error("unknown type: " + type);
    for (t = this._[type], i = 0, n = t.length; i < n; ++i) t[i].value.apply(that, args);
  },
  apply: function(type, that, args) {
    if (!this._.hasOwnProperty(type)) throw new Error("unknown type: " + type);
    for (var t = this._[type], i = 0, n = t.length; i < n; ++i) t[i].value.apply(that, args);
  }
};
function get$1(type, name) {
  for (var i = 0, n = type.length, c; i < n; ++i) {
    if ((c = type[i]).name === name) {
      return c.value;
    }
  }
}
function set$1(type, name, callback) {
  for (var i = 0, n = type.length; i < n; ++i) {
    if (type[i].name === name) {
      type[i] = noop, type = type.slice(0, i).concat(type.slice(i + 1));
      break;
    }
  }
  if (callback != null) type.push({ name, value: callback });
  return type;
}
var xhtml = "http://www.w3.org/1999/xhtml";
var namespaces = {
  svg: "http://www.w3.org/2000/svg",
  xhtml,
  xlink: "http://www.w3.org/1999/xlink",
  xml: "http://www.w3.org/XML/1998/namespace",
  xmlns: "http://www.w3.org/2000/xmlns/"
};
function namespace(name) {
  var prefix = name += "", i = prefix.indexOf(":");
  if (i >= 0 && (prefix = name.slice(0, i)) !== "xmlns") name = name.slice(i + 1);
  return namespaces.hasOwnProperty(prefix) ? { space: namespaces[prefix], local: name } : name;
}
function creatorInherit(name) {
  return function() {
    var document2 = this.ownerDocument, uri = this.namespaceURI;
    return uri === xhtml && document2.documentElement.namespaceURI === xhtml ? document2.createElement(name) : document2.createElementNS(uri, name);
  };
}
function creatorFixed(fullname) {
  return function() {
    return this.ownerDocument.createElementNS(fullname.space, fullname.local);
  };
}
function creator(name) {
  var fullname = namespace(name);
  return (fullname.local ? creatorFixed : creatorInherit)(fullname);
}
function none() {
}
function selector(selector2) {
  return selector2 == null ? none : function() {
    return this.querySelector(selector2);
  };
}
function selection_select(select2) {
  if (typeof select2 !== "function") select2 = selector(select2);
  for (var groups = this._groups, m = groups.length, subgroups = new Array(m), j = 0; j < m; ++j) {
    for (var group = groups[j], n = group.length, subgroup = subgroups[j] = new Array(n), node, subnode, i = 0; i < n; ++i) {
      if ((node = group[i]) && (subnode = select2.call(node, node.__data__, i, group))) {
        if ("__data__" in node) subnode.__data__ = node.__data__;
        subgroup[i] = subnode;
      }
    }
  }
  return new Selection$1(subgroups, this._parents);
}
function array$1(x2) {
  return x2 == null ? [] : Array.isArray(x2) ? x2 : Array.from(x2);
}
function empty() {
  return [];
}
function selectorAll(selector2) {
  return selector2 == null ? empty : function() {
    return this.querySelectorAll(selector2);
  };
}
function arrayAll(select2) {
  return function() {
    return array$1(select2.apply(this, arguments));
  };
}
function selection_selectAll(select2) {
  if (typeof select2 === "function") select2 = arrayAll(select2);
  else select2 = selectorAll(select2);
  for (var groups = this._groups, m = groups.length, subgroups = [], parents = [], j = 0; j < m; ++j) {
    for (var group = groups[j], n = group.length, node, i = 0; i < n; ++i) {
      if (node = group[i]) {
        subgroups.push(select2.call(node, node.__data__, i, group));
        parents.push(node);
      }
    }
  }
  return new Selection$1(subgroups, parents);
}
function matcher(selector2) {
  return function() {
    return this.matches(selector2);
  };
}
function childMatcher(selector2) {
  return function(node) {
    return node.matches(selector2);
  };
}
var find = Array.prototype.find;
function childFind(match) {
  return function() {
    return find.call(this.children, match);
  };
}
function childFirst() {
  return this.firstElementChild;
}
function selection_selectChild(match) {
  return this.select(match == null ? childFirst : childFind(typeof match === "function" ? match : childMatcher(match)));
}
var filter = Array.prototype.filter;
function children() {
  return Array.from(this.children);
}
function childrenFilter(match) {
  return function() {
    return filter.call(this.children, match);
  };
}
function selection_selectChildren(match) {
  return this.selectAll(match == null ? children : childrenFilter(typeof match === "function" ? match : childMatcher(match)));
}
function selection_filter(match) {
  if (typeof match !== "function") match = matcher(match);
  for (var groups = this._groups, m = groups.length, subgroups = new Array(m), j = 0; j < m; ++j) {
    for (var group = groups[j], n = group.length, subgroup = subgroups[j] = [], node, i = 0; i < n; ++i) {
      if ((node = group[i]) && match.call(node, node.__data__, i, group)) {
        subgroup.push(node);
      }
    }
  }
  return new Selection$1(subgroups, this._parents);
}
function sparse(update) {
  return new Array(update.length);
}
function selection_enter() {
  return new Selection$1(this._enter || this._groups.map(sparse), this._parents);
}
function EnterNode(parent, datum2) {
  this.ownerDocument = parent.ownerDocument;
  this.namespaceURI = parent.namespaceURI;
  this._next = null;
  this._parent = parent;
  this.__data__ = datum2;
}
EnterNode.prototype = {
  constructor: EnterNode,
  appendChild: function(child) {
    return this._parent.insertBefore(child, this._next);
  },
  insertBefore: function(child, next) {
    return this._parent.insertBefore(child, next);
  },
  querySelector: function(selector2) {
    return this._parent.querySelector(selector2);
  },
  querySelectorAll: function(selector2) {
    return this._parent.querySelectorAll(selector2);
  }
};
function constant$3(x2) {
  return function() {
    return x2;
  };
}
function bindIndex(parent, group, enter, update, exit, data) {
  var i = 0, node, groupLength = group.length, dataLength = data.length;
  for (; i < dataLength; ++i) {
    if (node = group[i]) {
      node.__data__ = data[i];
      update[i] = node;
    } else {
      enter[i] = new EnterNode(parent, data[i]);
    }
  }
  for (; i < groupLength; ++i) {
    if (node = group[i]) {
      exit[i] = node;
    }
  }
}
function bindKey(parent, group, enter, update, exit, data, key) {
  var i, node, nodeByKeyValue = /* @__PURE__ */ new Map(), groupLength = group.length, dataLength = data.length, keyValues = new Array(groupLength), keyValue;
  for (i = 0; i < groupLength; ++i) {
    if (node = group[i]) {
      keyValues[i] = keyValue = key.call(node, node.__data__, i, group) + "";
      if (nodeByKeyValue.has(keyValue)) {
        exit[i] = node;
      } else {
        nodeByKeyValue.set(keyValue, node);
      }
    }
  }
  for (i = 0; i < dataLength; ++i) {
    keyValue = key.call(parent, data[i], i, data) + "";
    if (node = nodeByKeyValue.get(keyValue)) {
      update[i] = node;
      node.__data__ = data[i];
      nodeByKeyValue.delete(keyValue);
    } else {
      enter[i] = new EnterNode(parent, data[i]);
    }
  }
  for (i = 0; i < groupLength; ++i) {
    if ((node = group[i]) && nodeByKeyValue.get(keyValues[i]) === node) {
      exit[i] = node;
    }
  }
}
function datum(node) {
  return node.__data__;
}
function selection_data(value, key) {
  if (!arguments.length) return Array.from(this, datum);
  var bind = key ? bindKey : bindIndex, parents = this._parents, groups = this._groups;
  if (typeof value !== "function") value = constant$3(value);
  for (var m = groups.length, update = new Array(m), enter = new Array(m), exit = new Array(m), j = 0; j < m; ++j) {
    var parent = parents[j], group = groups[j], groupLength = group.length, data = arraylike(value.call(parent, parent && parent.__data__, j, parents)), dataLength = data.length, enterGroup = enter[j] = new Array(dataLength), updateGroup = update[j] = new Array(dataLength), exitGroup = exit[j] = new Array(groupLength);
    bind(parent, group, enterGroup, updateGroup, exitGroup, data, key);
    for (var i0 = 0, i1 = 0, previous, next; i0 < dataLength; ++i0) {
      if (previous = enterGroup[i0]) {
        if (i0 >= i1) i1 = i0 + 1;
        while (!(next = updateGroup[i1]) && ++i1 < dataLength) ;
        previous._next = next || null;
      }
    }
  }
  update = new Selection$1(update, parents);
  update._enter = enter;
  update._exit = exit;
  return update;
}
function arraylike(data) {
  return typeof data === "object" && "length" in data ? data : Array.from(data);
}
function selection_exit() {
  return new Selection$1(this._exit || this._groups.map(sparse), this._parents);
}
function selection_join(onenter, onupdate, onexit) {
  var enter = this.enter(), update = this, exit = this.exit();
  if (typeof onenter === "function") {
    enter = onenter(enter);
    if (enter) enter = enter.selection();
  } else {
    enter = enter.append(onenter + "");
  }
  if (onupdate != null) {
    update = onupdate(update);
    if (update) update = update.selection();
  }
  if (onexit == null) exit.remove();
  else onexit(exit);
  return enter && update ? enter.merge(update).order() : update;
}
function selection_merge(context) {
  var selection2 = context.selection ? context.selection() : context;
  for (var groups0 = this._groups, groups1 = selection2._groups, m0 = groups0.length, m1 = groups1.length, m = Math.min(m0, m1), merges = new Array(m0), j = 0; j < m; ++j) {
    for (var group0 = groups0[j], group1 = groups1[j], n = group0.length, merge2 = merges[j] = new Array(n), node, i = 0; i < n; ++i) {
      if (node = group0[i] || group1[i]) {
        merge2[i] = node;
      }
    }
  }
  for (; j < m0; ++j) {
    merges[j] = groups0[j];
  }
  return new Selection$1(merges, this._parents);
}
function selection_order() {
  for (var groups = this._groups, j = -1, m = groups.length; ++j < m; ) {
    for (var group = groups[j], i = group.length - 1, next = group[i], node; --i >= 0; ) {
      if (node = group[i]) {
        if (next && node.compareDocumentPosition(next) ^ 4) next.parentNode.insertBefore(node, next);
        next = node;
      }
    }
  }
  return this;
}
function selection_sort(compare) {
  if (!compare) compare = ascending;
  function compareNode(a, b) {
    return a && b ? compare(a.__data__, b.__data__) : !a - !b;
  }
  for (var groups = this._groups, m = groups.length, sortgroups = new Array(m), j = 0; j < m; ++j) {
    for (var group = groups[j], n = group.length, sortgroup = sortgroups[j] = new Array(n), node, i = 0; i < n; ++i) {
      if (node = group[i]) {
        sortgroup[i] = node;
      }
    }
    sortgroup.sort(compareNode);
  }
  return new Selection$1(sortgroups, this._parents).order();
}
function ascending(a, b) {
  return a < b ? -1 : a > b ? 1 : a >= b ? 0 : NaN;
}
function selection_call() {
  var callback = arguments[0];
  arguments[0] = this;
  callback.apply(null, arguments);
  return this;
}
function selection_nodes() {
  return Array.from(this);
}
function selection_node() {
  for (var groups = this._groups, j = 0, m = groups.length; j < m; ++j) {
    for (var group = groups[j], i = 0, n = group.length; i < n; ++i) {
      var node = group[i];
      if (node) return node;
    }
  }
  return null;
}
function selection_size() {
  let size = 0;
  for (const node of this) ++size;
  return size;
}
function selection_empty() {
  return !this.node();
}
function selection_each(callback) {
  for (var groups = this._groups, j = 0, m = groups.length; j < m; ++j) {
    for (var group = groups[j], i = 0, n = group.length, node; i < n; ++i) {
      if (node = group[i]) callback.call(node, node.__data__, i, group);
    }
  }
  return this;
}
function attrRemove$1(name) {
  return function() {
    this.removeAttribute(name);
  };
}
function attrRemoveNS$1(fullname) {
  return function() {
    this.removeAttributeNS(fullname.space, fullname.local);
  };
}
function attrConstant$1(name, value) {
  return function() {
    this.setAttribute(name, value);
  };
}
function attrConstantNS$1(fullname, value) {
  return function() {
    this.setAttributeNS(fullname.space, fullname.local, value);
  };
}
function attrFunction$1(name, value) {
  return function() {
    var v = value.apply(this, arguments);
    if (v == null) this.removeAttribute(name);
    else this.setAttribute(name, v);
  };
}
function attrFunctionNS$1(fullname, value) {
  return function() {
    var v = value.apply(this, arguments);
    if (v == null) this.removeAttributeNS(fullname.space, fullname.local);
    else this.setAttributeNS(fullname.space, fullname.local, v);
  };
}
function selection_attr(name, value) {
  var fullname = namespace(name);
  if (arguments.length < 2) {
    var node = this.node();
    return fullname.local ? node.getAttributeNS(fullname.space, fullname.local) : node.getAttribute(fullname);
  }
  return this.each((value == null ? fullname.local ? attrRemoveNS$1 : attrRemove$1 : typeof value === "function" ? fullname.local ? attrFunctionNS$1 : attrFunction$1 : fullname.local ? attrConstantNS$1 : attrConstant$1)(fullname, value));
}
function defaultView(node) {
  return node.ownerDocument && node.ownerDocument.defaultView || node.document && node || node.defaultView;
}
function styleRemove$1(name) {
  return function() {
    this.style.removeProperty(name);
  };
}
function styleConstant$1(name, value, priority) {
  return function() {
    this.style.setProperty(name, value, priority);
  };
}
function styleFunction$1(name, value, priority) {
  return function() {
    var v = value.apply(this, arguments);
    if (v == null) this.style.removeProperty(name);
    else this.style.setProperty(name, v, priority);
  };
}
function selection_style(name, value, priority) {
  return arguments.length > 1 ? this.each((value == null ? styleRemove$1 : typeof value === "function" ? styleFunction$1 : styleConstant$1)(name, value, priority == null ? "" : priority)) : styleValue(this.node(), name);
}
function styleValue(node, name) {
  return node.style.getPropertyValue(name) || defaultView(node).getComputedStyle(node, null).getPropertyValue(name);
}
function propertyRemove(name) {
  return function() {
    delete this[name];
  };
}
function propertyConstant(name, value) {
  return function() {
    this[name] = value;
  };
}
function propertyFunction(name, value) {
  return function() {
    var v = value.apply(this, arguments);
    if (v == null) delete this[name];
    else this[name] = v;
  };
}
function selection_property(name, value) {
  return arguments.length > 1 ? this.each((value == null ? propertyRemove : typeof value === "function" ? propertyFunction : propertyConstant)(name, value)) : this.node()[name];
}
function classArray(string) {
  return string.trim().split(/^|\s+/);
}
function classList(node) {
  return node.classList || new ClassList(node);
}
function ClassList(node) {
  this._node = node;
  this._names = classArray(node.getAttribute("class") || "");
}
ClassList.prototype = {
  add: function(name) {
    var i = this._names.indexOf(name);
    if (i < 0) {
      this._names.push(name);
      this._node.setAttribute("class", this._names.join(" "));
    }
  },
  remove: function(name) {
    var i = this._names.indexOf(name);
    if (i >= 0) {
      this._names.splice(i, 1);
      this._node.setAttribute("class", this._names.join(" "));
    }
  },
  contains: function(name) {
    return this._names.indexOf(name) >= 0;
  }
};
function classedAdd(node, names) {
  var list = classList(node), i = -1, n = names.length;
  while (++i < n) list.add(names[i]);
}
function classedRemove(node, names) {
  var list = classList(node), i = -1, n = names.length;
  while (++i < n) list.remove(names[i]);
}
function classedTrue(names) {
  return function() {
    classedAdd(this, names);
  };
}
function classedFalse(names) {
  return function() {
    classedRemove(this, names);
  };
}
function classedFunction(names, value) {
  return function() {
    (value.apply(this, arguments) ? classedAdd : classedRemove)(this, names);
  };
}
function selection_classed(name, value) {
  var names = classArray(name + "");
  if (arguments.length < 2) {
    var list = classList(this.node()), i = -1, n = names.length;
    while (++i < n) if (!list.contains(names[i])) return false;
    return true;
  }
  return this.each((typeof value === "function" ? classedFunction : value ? classedTrue : classedFalse)(names, value));
}
function textRemove() {
  this.textContent = "";
}
function textConstant$1(value) {
  return function() {
    this.textContent = value;
  };
}
function textFunction$1(value) {
  return function() {
    var v = value.apply(this, arguments);
    this.textContent = v == null ? "" : v;
  };
}
function selection_text(value) {
  return arguments.length ? this.each(value == null ? textRemove : (typeof value === "function" ? textFunction$1 : textConstant$1)(value)) : this.node().textContent;
}
function htmlRemove() {
  this.innerHTML = "";
}
function htmlConstant(value) {
  return function() {
    this.innerHTML = value;
  };
}
function htmlFunction(value) {
  return function() {
    var v = value.apply(this, arguments);
    this.innerHTML = v == null ? "" : v;
  };
}
function selection_html(value) {
  return arguments.length ? this.each(value == null ? htmlRemove : (typeof value === "function" ? htmlFunction : htmlConstant)(value)) : this.node().innerHTML;
}
function raise() {
  if (this.nextSibling) this.parentNode.appendChild(this);
}
function selection_raise() {
  return this.each(raise);
}
function lower() {
  if (this.previousSibling) this.parentNode.insertBefore(this, this.parentNode.firstChild);
}
function selection_lower() {
  return this.each(lower);
}
function selection_append(name) {
  var create2 = typeof name === "function" ? name : creator(name);
  return this.select(function() {
    return this.appendChild(create2.apply(this, arguments));
  });
}
function constantNull() {
  return null;
}
function selection_insert(name, before) {
  var create2 = typeof name === "function" ? name : creator(name), select2 = before == null ? constantNull : typeof before === "function" ? before : selector(before);
  return this.select(function() {
    return this.insertBefore(create2.apply(this, arguments), select2.apply(this, arguments) || null);
  });
}
function remove() {
  var parent = this.parentNode;
  if (parent) parent.removeChild(this);
}
function selection_remove() {
  return this.each(remove);
}
function selection_cloneShallow() {
  var clone = this.cloneNode(false), parent = this.parentNode;
  return parent ? parent.insertBefore(clone, this.nextSibling) : clone;
}
function selection_cloneDeep() {
  var clone = this.cloneNode(true), parent = this.parentNode;
  return parent ? parent.insertBefore(clone, this.nextSibling) : clone;
}
function selection_clone(deep) {
  return this.select(deep ? selection_cloneDeep : selection_cloneShallow);
}
function selection_datum(value) {
  return arguments.length ? this.property("__data__", value) : this.node().__data__;
}
function contextListener(listener) {
  return function(event) {
    listener.call(this, event, this.__data__);
  };
}
function parseTypenames(typenames) {
  return typenames.trim().split(/^|\s+/).map(function(t) {
    var name = "", i = t.indexOf(".");
    if (i >= 0) name = t.slice(i + 1), t = t.slice(0, i);
    return { type: t, name };
  });
}
function onRemove(typename) {
  return function() {
    var on = this.__on;
    if (!on) return;
    for (var j = 0, i = -1, m = on.length, o; j < m; ++j) {
      if (o = on[j], (!typename.type || o.type === typename.type) && o.name === typename.name) {
        this.removeEventListener(o.type, o.listener, o.options);
      } else {
        on[++i] = o;
      }
    }
    if (++i) on.length = i;
    else delete this.__on;
  };
}
function onAdd(typename, value, options2) {
  return function() {
    var on = this.__on, o, listener = contextListener(value);
    if (on) for (var j = 0, m = on.length; j < m; ++j) {
      if ((o = on[j]).type === typename.type && o.name === typename.name) {
        this.removeEventListener(o.type, o.listener, o.options);
        this.addEventListener(o.type, o.listener = listener, o.options = options2);
        o.value = value;
        return;
      }
    }
    this.addEventListener(typename.type, listener, options2);
    o = { type: typename.type, name: typename.name, value, listener, options: options2 };
    if (!on) this.__on = [o];
    else on.push(o);
  };
}
function selection_on(typename, value, options2) {
  var typenames = parseTypenames(typename + ""), i, n = typenames.length, t;
  if (arguments.length < 2) {
    var on = this.node().__on;
    if (on) for (var j = 0, m = on.length, o; j < m; ++j) {
      for (i = 0, o = on[j]; i < n; ++i) {
        if ((t = typenames[i]).type === o.type && t.name === o.name) {
          return o.value;
        }
      }
    }
    return;
  }
  on = value ? onAdd : onRemove;
  for (i = 0; i < n; ++i) this.each(on(typenames[i], value, options2));
  return this;
}
function dispatchEvent(node, type, params) {
  var window2 = defaultView(node), event = window2.CustomEvent;
  if (typeof event === "function") {
    event = new event(type, params);
  } else {
    event = window2.document.createEvent("Event");
    if (params) event.initEvent(type, params.bubbles, params.cancelable), event.detail = params.detail;
    else event.initEvent(type, false, false);
  }
  node.dispatchEvent(event);
}
function dispatchConstant(type, params) {
  return function() {
    return dispatchEvent(this, type, params);
  };
}
function dispatchFunction(type, params) {
  return function() {
    return dispatchEvent(this, type, params.apply(this, arguments));
  };
}
function selection_dispatch(type, params) {
  return this.each((typeof params === "function" ? dispatchFunction : dispatchConstant)(type, params));
}
function* selection_iterator() {
  for (var groups = this._groups, j = 0, m = groups.length; j < m; ++j) {
    for (var group = groups[j], i = 0, n = group.length, node; i < n; ++i) {
      if (node = group[i]) yield node;
    }
  }
}
var root = [null];
function Selection$1(groups, parents) {
  this._groups = groups;
  this._parents = parents;
}
function selection() {
  return new Selection$1([[document.documentElement]], root);
}
function selection_selection() {
  return this;
}
Selection$1.prototype = selection.prototype = {
  constructor: Selection$1,
  select: selection_select,
  selectAll: selection_selectAll,
  selectChild: selection_selectChild,
  selectChildren: selection_selectChildren,
  filter: selection_filter,
  data: selection_data,
  enter: selection_enter,
  exit: selection_exit,
  join: selection_join,
  merge: selection_merge,
  selection: selection_selection,
  order: selection_order,
  sort: selection_sort,
  call: selection_call,
  nodes: selection_nodes,
  node: selection_node,
  size: selection_size,
  empty: selection_empty,
  each: selection_each,
  attr: selection_attr,
  style: selection_style,
  property: selection_property,
  classed: selection_classed,
  text: selection_text,
  html: selection_html,
  raise: selection_raise,
  lower: selection_lower,
  append: selection_append,
  insert: selection_insert,
  remove: selection_remove,
  clone: selection_clone,
  datum: selection_datum,
  on: selection_on,
  dispatch: selection_dispatch,
  [Symbol.iterator]: selection_iterator
};
function select(selector2) {
  return typeof selector2 === "string" ? new Selection$1([[document.querySelector(selector2)]], [document.documentElement]) : new Selection$1([[selector2]], root);
}
function sourceEvent(event) {
  let sourceEvent2;
  while (sourceEvent2 = event.sourceEvent) event = sourceEvent2;
  return event;
}
function pointer(event, node) {
  event = sourceEvent(event);
  if (node === void 0) node = event.currentTarget;
  if (node) {
    var svg = node.ownerSVGElement || node;
    if (svg.createSVGPoint) {
      var point = svg.createSVGPoint();
      point.x = event.clientX, point.y = event.clientY;
      point = point.matrixTransform(node.getScreenCTM().inverse());
      return [point.x, point.y];
    }
    if (node.getBoundingClientRect) {
      var rect = node.getBoundingClientRect();
      return [event.clientX - rect.left - node.clientLeft, event.clientY - rect.top - node.clientTop];
    }
  }
  return [event.pageX, event.pageY];
}
const nonpassive = { passive: false };
const nonpassivecapture = { capture: true, passive: false };
function nopropagation(event) {
  event.stopImmediatePropagation();
}
function noevent(event) {
  event.preventDefault();
  event.stopImmediatePropagation();
}
function dragDisable(view) {
  var root2 = view.document.documentElement, selection2 = select(view).on("dragstart.drag", noevent, nonpassivecapture);
  if ("onselectstart" in root2) {
    selection2.on("selectstart.drag", noevent, nonpassivecapture);
  } else {
    root2.__noselect = root2.style.MozUserSelect;
    root2.style.MozUserSelect = "none";
  }
}
function yesdrag(view, noclick) {
  var root2 = view.document.documentElement, selection2 = select(view).on("dragstart.drag", null);
  if (noclick) {
    selection2.on("click.drag", noevent, nonpassivecapture);
    setTimeout(function() {
      selection2.on("click.drag", null);
    }, 0);
  }
  if ("onselectstart" in root2) {
    selection2.on("selectstart.drag", null);
  } else {
    root2.style.MozUserSelect = root2.__noselect;
    delete root2.__noselect;
  }
}
var constant$2 = (x2) => () => x2;
function DragEvent(type, {
  sourceEvent: sourceEvent2,
  subject,
  target,
  identifier,
  active,
  x: x2,
  y: y2,
  dx,
  dy,
  dispatch: dispatch2
}) {
  Object.defineProperties(this, {
    type: { value: type, enumerable: true, configurable: true },
    sourceEvent: { value: sourceEvent2, enumerable: true, configurable: true },
    subject: { value: subject, enumerable: true, configurable: true },
    target: { value: target, enumerable: true, configurable: true },
    identifier: { value: identifier, enumerable: true, configurable: true },
    active: { value: active, enumerable: true, configurable: true },
    x: { value: x2, enumerable: true, configurable: true },
    y: { value: y2, enumerable: true, configurable: true },
    dx: { value: dx, enumerable: true, configurable: true },
    dy: { value: dy, enumerable: true, configurable: true },
    _: { value: dispatch2 }
  });
}
DragEvent.prototype.on = function() {
  var value = this._.on.apply(this._, arguments);
  return value === this._ ? this : value;
};
function defaultFilter(event) {
  return !event.ctrlKey && !event.button;
}
function defaultContainer() {
  return this.parentNode;
}
function defaultSubject(event, d) {
  return d == null ? { x: event.x, y: event.y } : d;
}
function defaultTouchable() {
  return navigator.maxTouchPoints || "ontouchstart" in this;
}
function drag() {
  var filter2 = defaultFilter, container = defaultContainer, subject = defaultSubject, touchable = defaultTouchable, gestures = {}, listeners = dispatch("start", "drag", "end"), active = 0, mousedownx, mousedowny, mousemoving, touchending, clickDistance2 = 0;
  function drag2(selection2) {
    selection2.on("mousedown.drag", mousedowned).filter(touchable).on("touchstart.drag", touchstarted).on("touchmove.drag", touchmoved, nonpassive).on("touchend.drag touchcancel.drag", touchended).style("touch-action", "none").style("-webkit-tap-highlight-color", "rgba(0,0,0,0)");
  }
  function mousedowned(event, d) {
    if (touchending || !filter2.call(this, event, d)) return;
    var gesture = beforestart(this, container.call(this, event, d), event, d, "mouse");
    if (!gesture) return;
    select(event.view).on("mousemove.drag", mousemoved, nonpassivecapture).on("mouseup.drag", mouseupped, nonpassivecapture);
    dragDisable(event.view);
    nopropagation(event);
    mousemoving = false;
    mousedownx = event.clientX;
    mousedowny = event.clientY;
    gesture("start", event);
  }
  function mousemoved(event) {
    noevent(event);
    if (!mousemoving) {
      var dx = event.clientX - mousedownx, dy = event.clientY - mousedowny;
      mousemoving = dx * dx + dy * dy > clickDistance2;
    }
    gestures.mouse("drag", event);
  }
  function mouseupped(event) {
    select(event.view).on("mousemove.drag mouseup.drag", null);
    yesdrag(event.view, mousemoving);
    noevent(event);
    gestures.mouse("end", event);
  }
  function touchstarted(event, d) {
    if (!filter2.call(this, event, d)) return;
    var touches = event.changedTouches, c = container.call(this, event, d), n = touches.length, i, gesture;
    for (i = 0; i < n; ++i) {
      if (gesture = beforestart(this, c, event, d, touches[i].identifier, touches[i])) {
        nopropagation(event);
        gesture("start", event, touches[i]);
      }
    }
  }
  function touchmoved(event) {
    var touches = event.changedTouches, n = touches.length, i, gesture;
    for (i = 0; i < n; ++i) {
      if (gesture = gestures[touches[i].identifier]) {
        noevent(event);
        gesture("drag", event, touches[i]);
      }
    }
  }
  function touchended(event) {
    var touches = event.changedTouches, n = touches.length, i, gesture;
    if (touchending) clearTimeout(touchending);
    touchending = setTimeout(function() {
      touchending = null;
    }, 500);
    for (i = 0; i < n; ++i) {
      if (gesture = gestures[touches[i].identifier]) {
        nopropagation(event);
        gesture("end", event, touches[i]);
      }
    }
  }
  function beforestart(that, container2, event, d, identifier, touch) {
    var dispatch2 = listeners.copy(), p = pointer(touch || event, container2), dx, dy, s;
    if ((s = subject.call(that, new DragEvent("beforestart", {
      sourceEvent: event,
      target: drag2,
      identifier,
      active,
      x: p[0],
      y: p[1],
      dx: 0,
      dy: 0,
      dispatch: dispatch2
    }), d)) == null) return;
    dx = s.x - p[0] || 0;
    dy = s.y - p[1] || 0;
    return function gesture(type, event2, touch2) {
      var p0 = p, n;
      switch (type) {
        case "start":
          gestures[identifier] = gesture, n = active++;
          break;
        case "end":
          delete gestures[identifier], --active;
        // falls through
        case "drag":
          p = pointer(touch2 || event2, container2), n = active;
          break;
      }
      dispatch2.call(
        type,
        that,
        new DragEvent(type, {
          sourceEvent: event2,
          subject: s,
          target: drag2,
          identifier,
          active: n,
          x: p[0] + dx,
          y: p[1] + dy,
          dx: p[0] - p0[0],
          dy: p[1] - p0[1],
          dispatch: dispatch2
        }),
        d
      );
    };
  }
  drag2.filter = function(_2) {
    return arguments.length ? (filter2 = typeof _2 === "function" ? _2 : constant$2(!!_2), drag2) : filter2;
  };
  drag2.container = function(_2) {
    return arguments.length ? (container = typeof _2 === "function" ? _2 : constant$2(_2), drag2) : container;
  };
  drag2.subject = function(_2) {
    return arguments.length ? (subject = typeof _2 === "function" ? _2 : constant$2(_2), drag2) : subject;
  };
  drag2.touchable = function(_2) {
    return arguments.length ? (touchable = typeof _2 === "function" ? _2 : constant$2(!!_2), drag2) : touchable;
  };
  drag2.on = function() {
    var value = listeners.on.apply(listeners, arguments);
    return value === listeners ? drag2 : value;
  };
  drag2.clickDistance = function(_2) {
    return arguments.length ? (clickDistance2 = (_2 = +_2) * _2, drag2) : Math.sqrt(clickDistance2);
  };
  return drag2;
}
function define(constructor, factory, prototype) {
  constructor.prototype = factory.prototype = prototype;
  prototype.constructor = constructor;
}
function extend(parent, definition) {
  var prototype = Object.create(parent.prototype);
  for (var key in definition) prototype[key] = definition[key];
  return prototype;
}
function Color() {
}
var darker = 0.7;
var brighter = 1 / darker;
var reI = "\\s*([+-]?\\d+)\\s*", reN = "\\s*([+-]?(?:\\d*\\.)?\\d+(?:[eE][+-]?\\d+)?)\\s*", reP = "\\s*([+-]?(?:\\d*\\.)?\\d+(?:[eE][+-]?\\d+)?)%\\s*", reHex = /^#([0-9a-f]{3,8})$/, reRgbInteger = new RegExp(`^rgb\\(${reI},${reI},${reI}\\)$`), reRgbPercent = new RegExp(`^rgb\\(${reP},${reP},${reP}\\)$`), reRgbaInteger = new RegExp(`^rgba\\(${reI},${reI},${reI},${reN}\\)$`), reRgbaPercent = new RegExp(`^rgba\\(${reP},${reP},${reP},${reN}\\)$`), reHslPercent = new RegExp(`^hsl\\(${reN},${reP},${reP}\\)$`), reHslaPercent = new RegExp(`^hsla\\(${reN},${reP},${reP},${reN}\\)$`);
var named = {
  aliceblue: 15792383,
  antiquewhite: 16444375,
  aqua: 65535,
  aquamarine: 8388564,
  azure: 15794175,
  beige: 16119260,
  bisque: 16770244,
  black: 0,
  blanchedalmond: 16772045,
  blue: 255,
  blueviolet: 9055202,
  brown: 10824234,
  burlywood: 14596231,
  cadetblue: 6266528,
  chartreuse: 8388352,
  chocolate: 13789470,
  coral: 16744272,
  cornflowerblue: 6591981,
  cornsilk: 16775388,
  crimson: 14423100,
  cyan: 65535,
  darkblue: 139,
  darkcyan: 35723,
  darkgoldenrod: 12092939,
  darkgray: 11119017,
  darkgreen: 25600,
  darkgrey: 11119017,
  darkkhaki: 12433259,
  darkmagenta: 9109643,
  darkolivegreen: 5597999,
  darkorange: 16747520,
  darkorchid: 10040012,
  darkred: 9109504,
  darksalmon: 15308410,
  darkseagreen: 9419919,
  darkslateblue: 4734347,
  darkslategray: 3100495,
  darkslategrey: 3100495,
  darkturquoise: 52945,
  darkviolet: 9699539,
  deeppink: 16716947,
  deepskyblue: 49151,
  dimgray: 6908265,
  dimgrey: 6908265,
  dodgerblue: 2003199,
  firebrick: 11674146,
  floralwhite: 16775920,
  forestgreen: 2263842,
  fuchsia: 16711935,
  gainsboro: 14474460,
  ghostwhite: 16316671,
  gold: 16766720,
  goldenrod: 14329120,
  gray: 8421504,
  green: 32768,
  greenyellow: 11403055,
  grey: 8421504,
  honeydew: 15794160,
  hotpink: 16738740,
  indianred: 13458524,
  indigo: 4915330,
  ivory: 16777200,
  khaki: 15787660,
  lavender: 15132410,
  lavenderblush: 16773365,
  lawngreen: 8190976,
  lemonchiffon: 16775885,
  lightblue: 11393254,
  lightcoral: 15761536,
  lightcyan: 14745599,
  lightgoldenrodyellow: 16448210,
  lightgray: 13882323,
  lightgreen: 9498256,
  lightgrey: 13882323,
  lightpink: 16758465,
  lightsalmon: 16752762,
  lightseagreen: 2142890,
  lightskyblue: 8900346,
  lightslategray: 7833753,
  lightslategrey: 7833753,
  lightsteelblue: 11584734,
  lightyellow: 16777184,
  lime: 65280,
  limegreen: 3329330,
  linen: 16445670,
  magenta: 16711935,
  maroon: 8388608,
  mediumaquamarine: 6737322,
  mediumblue: 205,
  mediumorchid: 12211667,
  mediumpurple: 9662683,
  mediumseagreen: 3978097,
  mediumslateblue: 8087790,
  mediumspringgreen: 64154,
  mediumturquoise: 4772300,
  mediumvioletred: 13047173,
  midnightblue: 1644912,
  mintcream: 16121850,
  mistyrose: 16770273,
  moccasin: 16770229,
  navajowhite: 16768685,
  navy: 128,
  oldlace: 16643558,
  olive: 8421376,
  olivedrab: 7048739,
  orange: 16753920,
  orangered: 16729344,
  orchid: 14315734,
  palegoldenrod: 15657130,
  palegreen: 10025880,
  paleturquoise: 11529966,
  palevioletred: 14381203,
  papayawhip: 16773077,
  peachpuff: 16767673,
  peru: 13468991,
  pink: 16761035,
  plum: 14524637,
  powderblue: 11591910,
  purple: 8388736,
  rebeccapurple: 6697881,
  red: 16711680,
  rosybrown: 12357519,
  royalblue: 4286945,
  saddlebrown: 9127187,
  salmon: 16416882,
  sandybrown: 16032864,
  seagreen: 3050327,
  seashell: 16774638,
  sienna: 10506797,
  silver: 12632256,
  skyblue: 8900331,
  slateblue: 6970061,
  slategray: 7372944,
  slategrey: 7372944,
  snow: 16775930,
  springgreen: 65407,
  steelblue: 4620980,
  tan: 13808780,
  teal: 32896,
  thistle: 14204888,
  tomato: 16737095,
  turquoise: 4251856,
  violet: 15631086,
  wheat: 16113331,
  white: 16777215,
  whitesmoke: 16119285,
  yellow: 16776960,
  yellowgreen: 10145074
};
define(Color, color, {
  copy(channels) {
    return Object.assign(new this.constructor(), this, channels);
  },
  displayable() {
    return this.rgb().displayable();
  },
  hex: color_formatHex,
  // Deprecated! Use color.formatHex.
  formatHex: color_formatHex,
  formatHex8: color_formatHex8,
  formatHsl: color_formatHsl,
  formatRgb: color_formatRgb,
  toString: color_formatRgb
});
function color_formatHex() {
  return this.rgb().formatHex();
}
function color_formatHex8() {
  return this.rgb().formatHex8();
}
function color_formatHsl() {
  return hslConvert(this).formatHsl();
}
function color_formatRgb() {
  return this.rgb().formatRgb();
}
function color(format2) {
  var m, l;
  format2 = (format2 + "").trim().toLowerCase();
  return (m = reHex.exec(format2)) ? (l = m[1].length, m = parseInt(m[1], 16), l === 6 ? rgbn(m) : l === 3 ? new Rgb(m >> 8 & 15 | m >> 4 & 240, m >> 4 & 15 | m & 240, (m & 15) << 4 | m & 15, 1) : l === 8 ? rgba(m >> 24 & 255, m >> 16 & 255, m >> 8 & 255, (m & 255) / 255) : l === 4 ? rgba(m >> 12 & 15 | m >> 8 & 240, m >> 8 & 15 | m >> 4 & 240, m >> 4 & 15 | m & 240, ((m & 15) << 4 | m & 15) / 255) : null) : (m = reRgbInteger.exec(format2)) ? new Rgb(m[1], m[2], m[3], 1) : (m = reRgbPercent.exec(format2)) ? new Rgb(m[1] * 255 / 100, m[2] * 255 / 100, m[3] * 255 / 100, 1) : (m = reRgbaInteger.exec(format2)) ? rgba(m[1], m[2], m[3], m[4]) : (m = reRgbaPercent.exec(format2)) ? rgba(m[1] * 255 / 100, m[2] * 255 / 100, m[3] * 255 / 100, m[4]) : (m = reHslPercent.exec(format2)) ? hsla(m[1], m[2] / 100, m[3] / 100, 1) : (m = reHslaPercent.exec(format2)) ? hsla(m[1], m[2] / 100, m[3] / 100, m[4]) : named.hasOwnProperty(format2) ? rgbn(named[format2]) : format2 === "transparent" ? new Rgb(NaN, NaN, NaN, 0) : null;
}
function rgbn(n) {
  return new Rgb(n >> 16 & 255, n >> 8 & 255, n & 255, 1);
}
function rgba(r, g, b, a) {
  if (a <= 0) r = g = b = NaN;
  return new Rgb(r, g, b, a);
}
function rgbConvert(o) {
  if (!(o instanceof Color)) o = color(o);
  if (!o) return new Rgb();
  o = o.rgb();
  return new Rgb(o.r, o.g, o.b, o.opacity);
}
function rgb(r, g, b, opacity) {
  return arguments.length === 1 ? rgbConvert(r) : new Rgb(r, g, b, opacity == null ? 1 : opacity);
}
function Rgb(r, g, b, opacity) {
  this.r = +r;
  this.g = +g;
  this.b = +b;
  this.opacity = +opacity;
}
define(Rgb, rgb, extend(Color, {
  brighter(k) {
    k = k == null ? brighter : Math.pow(brighter, k);
    return new Rgb(this.r * k, this.g * k, this.b * k, this.opacity);
  },
  darker(k) {
    k = k == null ? darker : Math.pow(darker, k);
    return new Rgb(this.r * k, this.g * k, this.b * k, this.opacity);
  },
  rgb() {
    return this;
  },
  clamp() {
    return new Rgb(clampi(this.r), clampi(this.g), clampi(this.b), clampa(this.opacity));
  },
  displayable() {
    return -0.5 <= this.r && this.r < 255.5 && (-0.5 <= this.g && this.g < 255.5) && (-0.5 <= this.b && this.b < 255.5) && (0 <= this.opacity && this.opacity <= 1);
  },
  hex: rgb_formatHex,
  // Deprecated! Use color.formatHex.
  formatHex: rgb_formatHex,
  formatHex8: rgb_formatHex8,
  formatRgb: rgb_formatRgb,
  toString: rgb_formatRgb
}));
function rgb_formatHex() {
  return `#${hex(this.r)}${hex(this.g)}${hex(this.b)}`;
}
function rgb_formatHex8() {
  return `#${hex(this.r)}${hex(this.g)}${hex(this.b)}${hex((isNaN(this.opacity) ? 1 : this.opacity) * 255)}`;
}
function rgb_formatRgb() {
  const a = clampa(this.opacity);
  return `${a === 1 ? "rgb(" : "rgba("}${clampi(this.r)}, ${clampi(this.g)}, ${clampi(this.b)}${a === 1 ? ")" : `, ${a})`}`;
}
function clampa(opacity) {
  return isNaN(opacity) ? 1 : Math.max(0, Math.min(1, opacity));
}
function clampi(value) {
  return Math.max(0, Math.min(255, Math.round(value) || 0));
}
function hex(value) {
  value = clampi(value);
  return (value < 16 ? "0" : "") + value.toString(16);
}
function hsla(h, s, l, a) {
  if (a <= 0) h = s = l = NaN;
  else if (l <= 0 || l >= 1) h = s = NaN;
  else if (s <= 0) h = NaN;
  return new Hsl(h, s, l, a);
}
function hslConvert(o) {
  if (o instanceof Hsl) return new Hsl(o.h, o.s, o.l, o.opacity);
  if (!(o instanceof Color)) o = color(o);
  if (!o) return new Hsl();
  if (o instanceof Hsl) return o;
  o = o.rgb();
  var r = o.r / 255, g = o.g / 255, b = o.b / 255, min = Math.min(r, g, b), max = Math.max(r, g, b), h = NaN, s = max - min, l = (max + min) / 2;
  if (s) {
    if (r === max) h = (g - b) / s + (g < b) * 6;
    else if (g === max) h = (b - r) / s + 2;
    else h = (r - g) / s + 4;
    s /= l < 0.5 ? max + min : 2 - max - min;
    h *= 60;
  } else {
    s = l > 0 && l < 1 ? 0 : h;
  }
  return new Hsl(h, s, l, o.opacity);
}
function hsl(h, s, l, opacity) {
  return arguments.length === 1 ? hslConvert(h) : new Hsl(h, s, l, opacity == null ? 1 : opacity);
}
function Hsl(h, s, l, opacity) {
  this.h = +h;
  this.s = +s;
  this.l = +l;
  this.opacity = +opacity;
}
define(Hsl, hsl, extend(Color, {
  brighter(k) {
    k = k == null ? brighter : Math.pow(brighter, k);
    return new Hsl(this.h, this.s, this.l * k, this.opacity);
  },
  darker(k) {
    k = k == null ? darker : Math.pow(darker, k);
    return new Hsl(this.h, this.s, this.l * k, this.opacity);
  },
  rgb() {
    var h = this.h % 360 + (this.h < 0) * 360, s = isNaN(h) || isNaN(this.s) ? 0 : this.s, l = this.l, m2 = l + (l < 0.5 ? l : 1 - l) * s, m1 = 2 * l - m2;
    return new Rgb(
      hsl2rgb(h >= 240 ? h - 240 : h + 120, m1, m2),
      hsl2rgb(h, m1, m2),
      hsl2rgb(h < 120 ? h + 240 : h - 120, m1, m2),
      this.opacity
    );
  },
  clamp() {
    return new Hsl(clamph(this.h), clampt(this.s), clampt(this.l), clampa(this.opacity));
  },
  displayable() {
    return (0 <= this.s && this.s <= 1 || isNaN(this.s)) && (0 <= this.l && this.l <= 1) && (0 <= this.opacity && this.opacity <= 1);
  },
  formatHsl() {
    const a = clampa(this.opacity);
    return `${a === 1 ? "hsl(" : "hsla("}${clamph(this.h)}, ${clampt(this.s) * 100}%, ${clampt(this.l) * 100}%${a === 1 ? ")" : `, ${a})`}`;
  }
}));
function clamph(value) {
  value = (value || 0) % 360;
  return value < 0 ? value + 360 : value;
}
function clampt(value) {
  return Math.max(0, Math.min(1, value || 0));
}
function hsl2rgb(h, m1, m2) {
  return (h < 60 ? m1 + (m2 - m1) * h / 60 : h < 180 ? m2 : h < 240 ? m1 + (m2 - m1) * (240 - h) / 60 : m1) * 255;
}
var constant$1 = (x2) => () => x2;
function linear$1(a, d) {
  return function(t) {
    return a + t * d;
  };
}
function exponential(a, b, y2) {
  return a = Math.pow(a, y2), b = Math.pow(b, y2) - a, y2 = 1 / y2, function(t) {
    return Math.pow(a + t * b, y2);
  };
}
function gamma(y2) {
  return (y2 = +y2) === 1 ? nogamma : function(a, b) {
    return b - a ? exponential(a, b, y2) : constant$1(isNaN(a) ? b : a);
  };
}
function nogamma(a, b) {
  var d = b - a;
  return d ? linear$1(a, d) : constant$1(isNaN(a) ? b : a);
}
var interpolateRgb = (function rgbGamma(y2) {
  var color2 = gamma(y2);
  function rgb$1(start2, end) {
    var r = color2((start2 = rgb(start2)).r, (end = rgb(end)).r), g = color2(start2.g, end.g), b = color2(start2.b, end.b), opacity = nogamma(start2.opacity, end.opacity);
    return function(t) {
      start2.r = r(t);
      start2.g = g(t);
      start2.b = b(t);
      start2.opacity = opacity(t);
      return start2 + "";
    };
  }
  rgb$1.gamma = rgbGamma;
  return rgb$1;
})(1);
function numberArray(a, b) {
  if (!b) b = [];
  var n = a ? Math.min(b.length, a.length) : 0, c = b.slice(), i;
  return function(t) {
    for (i = 0; i < n; ++i) c[i] = a[i] * (1 - t) + b[i] * t;
    return c;
  };
}
function isNumberArray(x2) {
  return ArrayBuffer.isView(x2) && !(x2 instanceof DataView);
}
function genericArray(a, b) {
  var nb = b ? b.length : 0, na = a ? Math.min(nb, a.length) : 0, x2 = new Array(na), c = new Array(nb), i;
  for (i = 0; i < na; ++i) x2[i] = interpolate$1(a[i], b[i]);
  for (; i < nb; ++i) c[i] = b[i];
  return function(t) {
    for (i = 0; i < na; ++i) c[i] = x2[i](t);
    return c;
  };
}
function date(a, b) {
  var d = /* @__PURE__ */ new Date();
  return a = +a, b = +b, function(t) {
    return d.setTime(a * (1 - t) + b * t), d;
  };
}
function interpolateNumber(a, b) {
  return a = +a, b = +b, function(t) {
    return a * (1 - t) + b * t;
  };
}
function object(a, b) {
  var i = {}, c = {}, k;
  if (a === null || typeof a !== "object") a = {};
  if (b === null || typeof b !== "object") b = {};
  for (k in b) {
    if (k in a) {
      i[k] = interpolate$1(a[k], b[k]);
    } else {
      c[k] = b[k];
    }
  }
  return function(t) {
    for (k in i) c[k] = i[k](t);
    return c;
  };
}
var reA = /[-+]?(?:\d+\.?\d*|\.?\d+)(?:[eE][-+]?\d+)?/g, reB = new RegExp(reA.source, "g");
function zero(b) {
  return function() {
    return b;
  };
}
function one(b) {
  return function(t) {
    return b(t) + "";
  };
}
function interpolateString(a, b) {
  var bi = reA.lastIndex = reB.lastIndex = 0, am, bm, bs, i = -1, s = [], q = [];
  a = a + "", b = b + "";
  while ((am = reA.exec(a)) && (bm = reB.exec(b))) {
    if ((bs = bm.index) > bi) {
      bs = b.slice(bi, bs);
      if (s[i]) s[i] += bs;
      else s[++i] = bs;
    }
    if ((am = am[0]) === (bm = bm[0])) {
      if (s[i]) s[i] += bm;
      else s[++i] = bm;
    } else {
      s[++i] = null;
      q.push({ i, x: interpolateNumber(am, bm) });
    }
    bi = reB.lastIndex;
  }
  if (bi < b.length) {
    bs = b.slice(bi);
    if (s[i]) s[i] += bs;
    else s[++i] = bs;
  }
  return s.length < 2 ? q[0] ? one(q[0].x) : zero(b) : (b = q.length, function(t) {
    for (var i2 = 0, o; i2 < b; ++i2) s[(o = q[i2]).i] = o.x(t);
    return s.join("");
  });
}
function interpolate$1(a, b) {
  var t = typeof b, c;
  return b == null || t === "boolean" ? constant$1(b) : (t === "number" ? interpolateNumber : t === "string" ? (c = color(b)) ? (b = c, interpolateRgb) : interpolateString : b instanceof color ? interpolateRgb : b instanceof Date ? date : isNumberArray(b) ? numberArray : Array.isArray(b) ? genericArray : typeof b.valueOf !== "function" && typeof b.toString !== "function" || isNaN(b) ? object : interpolateNumber)(a, b);
}
function interpolateRound(a, b) {
  return a = +a, b = +b, function(t) {
    return Math.round(a * (1 - t) + b * t);
  };
}
var degrees = 180 / Math.PI;
var identity$2 = {
  translateX: 0,
  translateY: 0,
  rotate: 0,
  skewX: 0,
  scaleX: 1,
  scaleY: 1
};
function decompose(a, b, c, d, e, f) {
  var scaleX, scaleY, skewX;
  if (scaleX = Math.sqrt(a * a + b * b)) a /= scaleX, b /= scaleX;
  if (skewX = a * c + b * d) c -= a * skewX, d -= b * skewX;
  if (scaleY = Math.sqrt(c * c + d * d)) c /= scaleY, d /= scaleY, skewX /= scaleY;
  if (a * d < b * c) a = -a, b = -b, skewX = -skewX, scaleX = -scaleX;
  return {
    translateX: e,
    translateY: f,
    rotate: Math.atan2(b, a) * degrees,
    skewX: Math.atan(skewX) * degrees,
    scaleX,
    scaleY
  };
}
var svgNode;
function parseCss(value) {
  const m = new (typeof DOMMatrix === "function" ? DOMMatrix : WebKitCSSMatrix)(value + "");
  return m.isIdentity ? identity$2 : decompose(m.a, m.b, m.c, m.d, m.e, m.f);
}
function parseSvg(value) {
  if (value == null) return identity$2;
  if (!svgNode) svgNode = document.createElementNS("http://www.w3.org/2000/svg", "g");
  svgNode.setAttribute("transform", value);
  if (!(value = svgNode.transform.baseVal.consolidate())) return identity$2;
  value = value.matrix;
  return decompose(value.a, value.b, value.c, value.d, value.e, value.f);
}
function interpolateTransform(parse, pxComma, pxParen, degParen) {
  function pop(s) {
    return s.length ? s.pop() + " " : "";
  }
  function translate(xa, ya, xb, yb, s, q) {
    if (xa !== xb || ya !== yb) {
      var i = s.push("translate(", null, pxComma, null, pxParen);
      q.push({ i: i - 4, x: interpolateNumber(xa, xb) }, { i: i - 2, x: interpolateNumber(ya, yb) });
    } else if (xb || yb) {
      s.push("translate(" + xb + pxComma + yb + pxParen);
    }
  }
  function rotate(a, b, s, q) {
    if (a !== b) {
      if (a - b > 180) b += 360;
      else if (b - a > 180) a += 360;
      q.push({ i: s.push(pop(s) + "rotate(", null, degParen) - 2, x: interpolateNumber(a, b) });
    } else if (b) {
      s.push(pop(s) + "rotate(" + b + degParen);
    }
  }
  function skewX(a, b, s, q) {
    if (a !== b) {
      q.push({ i: s.push(pop(s) + "skewX(", null, degParen) - 2, x: interpolateNumber(a, b) });
    } else if (b) {
      s.push(pop(s) + "skewX(" + b + degParen);
    }
  }
  function scale(xa, ya, xb, yb, s, q) {
    if (xa !== xb || ya !== yb) {
      var i = s.push(pop(s) + "scale(", null, ",", null, ")");
      q.push({ i: i - 4, x: interpolateNumber(xa, xb) }, { i: i - 2, x: interpolateNumber(ya, yb) });
    } else if (xb !== 1 || yb !== 1) {
      s.push(pop(s) + "scale(" + xb + "," + yb + ")");
    }
  }
  return function(a, b) {
    var s = [], q = [];
    a = parse(a), b = parse(b);
    translate(a.translateX, a.translateY, b.translateX, b.translateY, s, q);
    rotate(a.rotate, b.rotate, s, q);
    skewX(a.skewX, b.skewX, s, q);
    scale(a.scaleX, a.scaleY, b.scaleX, b.scaleY, s, q);
    a = b = null;
    return function(t) {
      var i = -1, n = q.length, o;
      while (++i < n) s[(o = q[i]).i] = o.x(t);
      return s.join("");
    };
  };
}
var interpolateTransformCss = interpolateTransform(parseCss, "px, ", "px)", "deg)");
var interpolateTransformSvg = interpolateTransform(parseSvg, ", ", ")", ")");
var frame = 0, timeout$1 = 0, interval = 0, pokeDelay = 1e3, taskHead, taskTail, clockLast = 0, clockNow = 0, clockSkew = 0, clock = typeof performance === "object" && performance.now ? performance : Date, setFrame = typeof window === "object" && window.requestAnimationFrame ? window.requestAnimationFrame.bind(window) : function(f) {
  setTimeout(f, 17);
};
function now() {
  return clockNow || (setFrame(clearNow), clockNow = clock.now() + clockSkew);
}
function clearNow() {
  clockNow = 0;
}
function Timer() {
  this._call = this._time = this._next = null;
}
Timer.prototype = timer.prototype = {
  constructor: Timer,
  restart: function(callback, delay, time) {
    if (typeof callback !== "function") throw new TypeError("callback is not a function");
    time = (time == null ? now() : +time) + (delay == null ? 0 : +delay);
    if (!this._next && taskTail !== this) {
      if (taskTail) taskTail._next = this;
      else taskHead = this;
      taskTail = this;
    }
    this._call = callback;
    this._time = time;
    sleep();
  },
  stop: function() {
    if (this._call) {
      this._call = null;
      this._time = Infinity;
      sleep();
    }
  }
};
function timer(callback, delay, time) {
  var t = new Timer();
  t.restart(callback, delay, time);
  return t;
}
function timerFlush() {
  now();
  ++frame;
  var t = taskHead, e;
  while (t) {
    if ((e = clockNow - t._time) >= 0) t._call.call(void 0, e);
    t = t._next;
  }
  --frame;
}
function wake() {
  clockNow = (clockLast = clock.now()) + clockSkew;
  frame = timeout$1 = 0;
  try {
    timerFlush();
  } finally {
    frame = 0;
    nap();
    clockNow = 0;
  }
}
function poke() {
  var now2 = clock.now(), delay = now2 - clockLast;
  if (delay > pokeDelay) clockSkew -= delay, clockLast = now2;
}
function nap() {
  var t0, t1 = taskHead, t2, time = Infinity;
  while (t1) {
    if (t1._call) {
      if (time > t1._time) time = t1._time;
      t0 = t1, t1 = t1._next;
    } else {
      t2 = t1._next, t1._next = null;
      t1 = t0 ? t0._next = t2 : taskHead = t2;
    }
  }
  taskTail = t0;
  sleep(time);
}
function sleep(time) {
  if (frame) return;
  if (timeout$1) timeout$1 = clearTimeout(timeout$1);
  var delay = time - clockNow;
  if (delay > 24) {
    if (time < Infinity) timeout$1 = setTimeout(wake, time - clock.now() - clockSkew);
    if (interval) interval = clearInterval(interval);
  } else {
    if (!interval) clockLast = clock.now(), interval = setInterval(poke, pokeDelay);
    frame = 1, setFrame(wake);
  }
}
function timeout(callback, delay, time) {
  var t = new Timer();
  delay = delay == null ? 0 : +delay;
  t.restart((elapsed) => {
    t.stop();
    callback(elapsed + delay);
  }, delay, time);
  return t;
}
var emptyOn = dispatch("start", "end", "cancel", "interrupt");
var emptyTween = [];
var CREATED = 0;
var SCHEDULED = 1;
var STARTING = 2;
var STARTED = 3;
var RUNNING = 4;
var ENDING = 5;
var ENDED = 6;
function schedule(node, name, id2, index, group, timing) {
  var schedules = node.__transition;
  if (!schedules) node.__transition = {};
  else if (id2 in schedules) return;
  create(node, id2, {
    name,
    index,
    // For context during callback.
    group,
    // For context during callback.
    on: emptyOn,
    tween: emptyTween,
    time: timing.time,
    delay: timing.delay,
    duration: timing.duration,
    ease: timing.ease,
    timer: null,
    state: CREATED
  });
}
function init(node, id2) {
  var schedule2 = get(node, id2);
  if (schedule2.state > CREATED) throw new Error("too late; already scheduled");
  return schedule2;
}
function set(node, id2) {
  var schedule2 = get(node, id2);
  if (schedule2.state > STARTED) throw new Error("too late; already running");
  return schedule2;
}
function get(node, id2) {
  var schedule2 = node.__transition;
  if (!schedule2 || !(schedule2 = schedule2[id2])) throw new Error("transition not found");
  return schedule2;
}
function create(node, id2, self) {
  var schedules = node.__transition, tween;
  schedules[id2] = self;
  self.timer = timer(schedule2, 0, self.time);
  function schedule2(elapsed) {
    self.state = SCHEDULED;
    self.timer.restart(start2, self.delay, self.time);
    if (self.delay <= elapsed) start2(elapsed - self.delay);
  }
  function start2(elapsed) {
    var i, j, n, o;
    if (self.state !== SCHEDULED) return stop();
    for (i in schedules) {
      o = schedules[i];
      if (o.name !== self.name) continue;
      if (o.state === STARTED) return timeout(start2);
      if (o.state === RUNNING) {
        o.state = ENDED;
        o.timer.stop();
        o.on.call("interrupt", node, node.__data__, o.index, o.group);
        delete schedules[i];
      } else if (+i < id2) {
        o.state = ENDED;
        o.timer.stop();
        o.on.call("cancel", node, node.__data__, o.index, o.group);
        delete schedules[i];
      }
    }
    timeout(function() {
      if (self.state === STARTED) {
        self.state = RUNNING;
        self.timer.restart(tick, self.delay, self.time);
        tick(elapsed);
      }
    });
    self.state = STARTING;
    self.on.call("start", node, node.__data__, self.index, self.group);
    if (self.state !== STARTING) return;
    self.state = STARTED;
    tween = new Array(n = self.tween.length);
    for (i = 0, j = -1; i < n; ++i) {
      if (o = self.tween[i].value.call(node, node.__data__, self.index, self.group)) {
        tween[++j] = o;
      }
    }
    tween.length = j + 1;
  }
  function tick(elapsed) {
    var t = elapsed < self.duration ? self.ease.call(null, elapsed / self.duration) : (self.timer.restart(stop), self.state = ENDING, 1), i = -1, n = tween.length;
    while (++i < n) {
      tween[i].call(node, t);
    }
    if (self.state === ENDING) {
      self.on.call("end", node, node.__data__, self.index, self.group);
      stop();
    }
  }
  function stop() {
    self.state = ENDED;
    self.timer.stop();
    delete schedules[id2];
    for (var i in schedules) return;
    delete node.__transition;
  }
}
function interrupt(node, name) {
  var schedules = node.__transition, schedule2, active, empty2 = true, i;
  if (!schedules) return;
  name = name == null ? null : name + "";
  for (i in schedules) {
    if ((schedule2 = schedules[i]).name !== name) {
      empty2 = false;
      continue;
    }
    active = schedule2.state > STARTING && schedule2.state < ENDING;
    schedule2.state = ENDED;
    schedule2.timer.stop();
    schedule2.on.call(active ? "interrupt" : "cancel", node, node.__data__, schedule2.index, schedule2.group);
    delete schedules[i];
  }
  if (empty2) delete node.__transition;
}
function selection_interrupt(name) {
  return this.each(function() {
    interrupt(this, name);
  });
}
function tweenRemove(id2, name) {
  var tween0, tween1;
  return function() {
    var schedule2 = set(this, id2), tween = schedule2.tween;
    if (tween !== tween0) {
      tween1 = tween0 = tween;
      for (var i = 0, n = tween1.length; i < n; ++i) {
        if (tween1[i].name === name) {
          tween1 = tween1.slice();
          tween1.splice(i, 1);
          break;
        }
      }
    }
    schedule2.tween = tween1;
  };
}
function tweenFunction(id2, name, value) {
  var tween0, tween1;
  if (typeof value !== "function") throw new Error();
  return function() {
    var schedule2 = set(this, id2), tween = schedule2.tween;
    if (tween !== tween0) {
      tween1 = (tween0 = tween).slice();
      for (var t = { name, value }, i = 0, n = tween1.length; i < n; ++i) {
        if (tween1[i].name === name) {
          tween1[i] = t;
          break;
        }
      }
      if (i === n) tween1.push(t);
    }
    schedule2.tween = tween1;
  };
}
function transition_tween(name, value) {
  var id2 = this._id;
  name += "";
  if (arguments.length < 2) {
    var tween = get(this.node(), id2).tween;
    for (var i = 0, n = tween.length, t; i < n; ++i) {
      if ((t = tween[i]).name === name) {
        return t.value;
      }
    }
    return null;
  }
  return this.each((value == null ? tweenRemove : tweenFunction)(id2, name, value));
}
function tweenValue(transition, name, value) {
  var id2 = transition._id;
  transition.each(function() {
    var schedule2 = set(this, id2);
    (schedule2.value || (schedule2.value = {}))[name] = value.apply(this, arguments);
  });
  return function(node) {
    return get(node, id2).value[name];
  };
}
function interpolate(a, b) {
  var c;
  return (typeof b === "number" ? interpolateNumber : b instanceof color ? interpolateRgb : (c = color(b)) ? (b = c, interpolateRgb) : interpolateString)(a, b);
}
function attrRemove(name) {
  return function() {
    this.removeAttribute(name);
  };
}
function attrRemoveNS(fullname) {
  return function() {
    this.removeAttributeNS(fullname.space, fullname.local);
  };
}
function attrConstant(name, interpolate2, value1) {
  var string00, string1 = value1 + "", interpolate0;
  return function() {
    var string0 = this.getAttribute(name);
    return string0 === string1 ? null : string0 === string00 ? interpolate0 : interpolate0 = interpolate2(string00 = string0, value1);
  };
}
function attrConstantNS(fullname, interpolate2, value1) {
  var string00, string1 = value1 + "", interpolate0;
  return function() {
    var string0 = this.getAttributeNS(fullname.space, fullname.local);
    return string0 === string1 ? null : string0 === string00 ? interpolate0 : interpolate0 = interpolate2(string00 = string0, value1);
  };
}
function attrFunction(name, interpolate2, value) {
  var string00, string10, interpolate0;
  return function() {
    var string0, value1 = value(this), string1;
    if (value1 == null) return void this.removeAttribute(name);
    string0 = this.getAttribute(name);
    string1 = value1 + "";
    return string0 === string1 ? null : string0 === string00 && string1 === string10 ? interpolate0 : (string10 = string1, interpolate0 = interpolate2(string00 = string0, value1));
  };
}
function attrFunctionNS(fullname, interpolate2, value) {
  var string00, string10, interpolate0;
  return function() {
    var string0, value1 = value(this), string1;
    if (value1 == null) return void this.removeAttributeNS(fullname.space, fullname.local);
    string0 = this.getAttributeNS(fullname.space, fullname.local);
    string1 = value1 + "";
    return string0 === string1 ? null : string0 === string00 && string1 === string10 ? interpolate0 : (string10 = string1, interpolate0 = interpolate2(string00 = string0, value1));
  };
}
function transition_attr(name, value) {
  var fullname = namespace(name), i = fullname === "transform" ? interpolateTransformSvg : interpolate;
  return this.attrTween(name, typeof value === "function" ? (fullname.local ? attrFunctionNS : attrFunction)(fullname, i, tweenValue(this, "attr." + name, value)) : value == null ? (fullname.local ? attrRemoveNS : attrRemove)(fullname) : (fullname.local ? attrConstantNS : attrConstant)(fullname, i, value));
}
function attrInterpolate(name, i) {
  return function(t) {
    this.setAttribute(name, i.call(this, t));
  };
}
function attrInterpolateNS(fullname, i) {
  return function(t) {
    this.setAttributeNS(fullname.space, fullname.local, i.call(this, t));
  };
}
function attrTweenNS(fullname, value) {
  var t0, i0;
  function tween() {
    var i = value.apply(this, arguments);
    if (i !== i0) t0 = (i0 = i) && attrInterpolateNS(fullname, i);
    return t0;
  }
  tween._value = value;
  return tween;
}
function attrTween(name, value) {
  var t0, i0;
  function tween() {
    var i = value.apply(this, arguments);
    if (i !== i0) t0 = (i0 = i) && attrInterpolate(name, i);
    return t0;
  }
  tween._value = value;
  return tween;
}
function transition_attrTween(name, value) {
  var key = "attr." + name;
  if (arguments.length < 2) return (key = this.tween(key)) && key._value;
  if (value == null) return this.tween(key, null);
  if (typeof value !== "function") throw new Error();
  var fullname = namespace(name);
  return this.tween(key, (fullname.local ? attrTweenNS : attrTween)(fullname, value));
}
function delayFunction(id2, value) {
  return function() {
    init(this, id2).delay = +value.apply(this, arguments);
  };
}
function delayConstant(id2, value) {
  return value = +value, function() {
    init(this, id2).delay = value;
  };
}
function transition_delay(value) {
  var id2 = this._id;
  return arguments.length ? this.each((typeof value === "function" ? delayFunction : delayConstant)(id2, value)) : get(this.node(), id2).delay;
}
function durationFunction(id2, value) {
  return function() {
    set(this, id2).duration = +value.apply(this, arguments);
  };
}
function durationConstant(id2, value) {
  return value = +value, function() {
    set(this, id2).duration = value;
  };
}
function transition_duration(value) {
  var id2 = this._id;
  return arguments.length ? this.each((typeof value === "function" ? durationFunction : durationConstant)(id2, value)) : get(this.node(), id2).duration;
}
function easeConstant(id2, value) {
  if (typeof value !== "function") throw new Error();
  return function() {
    set(this, id2).ease = value;
  };
}
function transition_ease(value) {
  var id2 = this._id;
  return arguments.length ? this.each(easeConstant(id2, value)) : get(this.node(), id2).ease;
}
function easeVarying(id2, value) {
  return function() {
    var v = value.apply(this, arguments);
    if (typeof v !== "function") throw new Error();
    set(this, id2).ease = v;
  };
}
function transition_easeVarying(value) {
  if (typeof value !== "function") throw new Error();
  return this.each(easeVarying(this._id, value));
}
function transition_filter(match) {
  if (typeof match !== "function") match = matcher(match);
  for (var groups = this._groups, m = groups.length, subgroups = new Array(m), j = 0; j < m; ++j) {
    for (var group = groups[j], n = group.length, subgroup = subgroups[j] = [], node, i = 0; i < n; ++i) {
      if ((node = group[i]) && match.call(node, node.__data__, i, group)) {
        subgroup.push(node);
      }
    }
  }
  return new Transition(subgroups, this._parents, this._name, this._id);
}
function transition_merge(transition) {
  if (transition._id !== this._id) throw new Error();
  for (var groups0 = this._groups, groups1 = transition._groups, m0 = groups0.length, m1 = groups1.length, m = Math.min(m0, m1), merges = new Array(m0), j = 0; j < m; ++j) {
    for (var group0 = groups0[j], group1 = groups1[j], n = group0.length, merge2 = merges[j] = new Array(n), node, i = 0; i < n; ++i) {
      if (node = group0[i] || group1[i]) {
        merge2[i] = node;
      }
    }
  }
  for (; j < m0; ++j) {
    merges[j] = groups0[j];
  }
  return new Transition(merges, this._parents, this._name, this._id);
}
function start(name) {
  return (name + "").trim().split(/^|\s+/).every(function(t) {
    var i = t.indexOf(".");
    if (i >= 0) t = t.slice(0, i);
    return !t || t === "start";
  });
}
function onFunction(id2, name, listener) {
  var on0, on1, sit = start(name) ? init : set;
  return function() {
    var schedule2 = sit(this, id2), on = schedule2.on;
    if (on !== on0) (on1 = (on0 = on).copy()).on(name, listener);
    schedule2.on = on1;
  };
}
function transition_on(name, listener) {
  var id2 = this._id;
  return arguments.length < 2 ? get(this.node(), id2).on.on(name) : this.each(onFunction(id2, name, listener));
}
function removeFunction(id2) {
  return function() {
    var parent = this.parentNode;
    for (var i in this.__transition) if (+i !== id2) return;
    if (parent) parent.removeChild(this);
  };
}
function transition_remove() {
  return this.on("end.remove", removeFunction(this._id));
}
function transition_select(select2) {
  var name = this._name, id2 = this._id;
  if (typeof select2 !== "function") select2 = selector(select2);
  for (var groups = this._groups, m = groups.length, subgroups = new Array(m), j = 0; j < m; ++j) {
    for (var group = groups[j], n = group.length, subgroup = subgroups[j] = new Array(n), node, subnode, i = 0; i < n; ++i) {
      if ((node = group[i]) && (subnode = select2.call(node, node.__data__, i, group))) {
        if ("__data__" in node) subnode.__data__ = node.__data__;
        subgroup[i] = subnode;
        schedule(subgroup[i], name, id2, i, subgroup, get(node, id2));
      }
    }
  }
  return new Transition(subgroups, this._parents, name, id2);
}
function transition_selectAll(select2) {
  var name = this._name, id2 = this._id;
  if (typeof select2 !== "function") select2 = selectorAll(select2);
  for (var groups = this._groups, m = groups.length, subgroups = [], parents = [], j = 0; j < m; ++j) {
    for (var group = groups[j], n = group.length, node, i = 0; i < n; ++i) {
      if (node = group[i]) {
        for (var children2 = select2.call(node, node.__data__, i, group), child, inherit2 = get(node, id2), k = 0, l = children2.length; k < l; ++k) {
          if (child = children2[k]) {
            schedule(child, name, id2, k, children2, inherit2);
          }
        }
        subgroups.push(children2);
        parents.push(node);
      }
    }
  }
  return new Transition(subgroups, parents, name, id2);
}
var Selection = selection.prototype.constructor;
function transition_selection() {
  return new Selection(this._groups, this._parents);
}
function styleNull(name, interpolate2) {
  var string00, string10, interpolate0;
  return function() {
    var string0 = styleValue(this, name), string1 = (this.style.removeProperty(name), styleValue(this, name));
    return string0 === string1 ? null : string0 === string00 && string1 === string10 ? interpolate0 : interpolate0 = interpolate2(string00 = string0, string10 = string1);
  };
}
function styleRemove(name) {
  return function() {
    this.style.removeProperty(name);
  };
}
function styleConstant(name, interpolate2, value1) {
  var string00, string1 = value1 + "", interpolate0;
  return function() {
    var string0 = styleValue(this, name);
    return string0 === string1 ? null : string0 === string00 ? interpolate0 : interpolate0 = interpolate2(string00 = string0, value1);
  };
}
function styleFunction(name, interpolate2, value) {
  var string00, string10, interpolate0;
  return function() {
    var string0 = styleValue(this, name), value1 = value(this), string1 = value1 + "";
    if (value1 == null) string1 = value1 = (this.style.removeProperty(name), styleValue(this, name));
    return string0 === string1 ? null : string0 === string00 && string1 === string10 ? interpolate0 : (string10 = string1, interpolate0 = interpolate2(string00 = string0, value1));
  };
}
function styleMaybeRemove(id2, name) {
  var on0, on1, listener0, key = "style." + name, event = "end." + key, remove2;
  return function() {
    var schedule2 = set(this, id2), on = schedule2.on, listener = schedule2.value[key] == null ? remove2 || (remove2 = styleRemove(name)) : void 0;
    if (on !== on0 || listener0 !== listener) (on1 = (on0 = on).copy()).on(event, listener0 = listener);
    schedule2.on = on1;
  };
}
function transition_style(name, value, priority) {
  var i = (name += "") === "transform" ? interpolateTransformCss : interpolate;
  return value == null ? this.styleTween(name, styleNull(name, i)).on("end.style." + name, styleRemove(name)) : typeof value === "function" ? this.styleTween(name, styleFunction(name, i, tweenValue(this, "style." + name, value))).each(styleMaybeRemove(this._id, name)) : this.styleTween(name, styleConstant(name, i, value), priority).on("end.style." + name, null);
}
function styleInterpolate(name, i, priority) {
  return function(t) {
    this.style.setProperty(name, i.call(this, t), priority);
  };
}
function styleTween(name, value, priority) {
  var t, i0;
  function tween() {
    var i = value.apply(this, arguments);
    if (i !== i0) t = (i0 = i) && styleInterpolate(name, i, priority);
    return t;
  }
  tween._value = value;
  return tween;
}
function transition_styleTween(name, value, priority) {
  var key = "style." + (name += "");
  if (arguments.length < 2) return (key = this.tween(key)) && key._value;
  if (value == null) return this.tween(key, null);
  if (typeof value !== "function") throw new Error();
  return this.tween(key, styleTween(name, value, priority == null ? "" : priority));
}
function textConstant(value) {
  return function() {
    this.textContent = value;
  };
}
function textFunction(value) {
  return function() {
    var value1 = value(this);
    this.textContent = value1 == null ? "" : value1;
  };
}
function transition_text(value) {
  return this.tween("text", typeof value === "function" ? textFunction(tweenValue(this, "text", value)) : textConstant(value == null ? "" : value + ""));
}
function textInterpolate(i) {
  return function(t) {
    this.textContent = i.call(this, t);
  };
}
function textTween(value) {
  var t0, i0;
  function tween() {
    var i = value.apply(this, arguments);
    if (i !== i0) t0 = (i0 = i) && textInterpolate(i);
    return t0;
  }
  tween._value = value;
  return tween;
}
function transition_textTween(value) {
  var key = "text";
  if (arguments.length < 1) return (key = this.tween(key)) && key._value;
  if (value == null) return this.tween(key, null);
  if (typeof value !== "function") throw new Error();
  return this.tween(key, textTween(value));
}
function transition_transition() {
  var name = this._name, id0 = this._id, id1 = newId();
  for (var groups = this._groups, m = groups.length, j = 0; j < m; ++j) {
    for (var group = groups[j], n = group.length, node, i = 0; i < n; ++i) {
      if (node = group[i]) {
        var inherit2 = get(node, id0);
        schedule(node, name, id1, i, group, {
          time: inherit2.time + inherit2.delay + inherit2.duration,
          delay: 0,
          duration: inherit2.duration,
          ease: inherit2.ease
        });
      }
    }
  }
  return new Transition(groups, this._parents, name, id1);
}
function transition_end() {
  var on0, on1, that = this, id2 = that._id, size = that.size();
  return new Promise(function(resolve, reject) {
    var cancel = { value: reject }, end = { value: function() {
      if (--size === 0) resolve();
    } };
    that.each(function() {
      var schedule2 = set(this, id2), on = schedule2.on;
      if (on !== on0) {
        on1 = (on0 = on).copy();
        on1._.cancel.push(cancel);
        on1._.interrupt.push(cancel);
        on1._.end.push(end);
      }
      schedule2.on = on1;
    });
    if (size === 0) resolve();
  });
}
var id = 0;
function Transition(groups, parents, name, id2) {
  this._groups = groups;
  this._parents = parents;
  this._name = name;
  this._id = id2;
}
function newId() {
  return ++id;
}
var selection_prototype = selection.prototype;
Transition.prototype = {
  constructor: Transition,
  select: transition_select,
  selectAll: transition_selectAll,
  selectChild: selection_prototype.selectChild,
  selectChildren: selection_prototype.selectChildren,
  filter: transition_filter,
  merge: transition_merge,
  selection: transition_selection,
  transition: transition_transition,
  call: selection_prototype.call,
  nodes: selection_prototype.nodes,
  node: selection_prototype.node,
  size: selection_prototype.size,
  empty: selection_prototype.empty,
  each: selection_prototype.each,
  on: transition_on,
  attr: transition_attr,
  attrTween: transition_attrTween,
  style: transition_style,
  styleTween: transition_styleTween,
  text: transition_text,
  textTween: transition_textTween,
  remove: transition_remove,
  tween: transition_tween,
  delay: transition_delay,
  duration: transition_duration,
  ease: transition_ease,
  easeVarying: transition_easeVarying,
  end: transition_end,
  [Symbol.iterator]: selection_prototype[Symbol.iterator]
};
function cubicInOut(t) {
  return ((t *= 2) <= 1 ? t * t * t : (t -= 2) * t * t + 2) / 2;
}
var defaultTiming = {
  time: null,
  // Set on use.
  delay: 0,
  duration: 250,
  ease: cubicInOut
};
function inherit(node, id2) {
  var timing;
  while (!(timing = node.__transition) || !(timing = timing[id2])) {
    if (!(node = node.parentNode)) {
      throw new Error(`transition ${id2} not found`);
    }
  }
  return timing;
}
function selection_transition(name) {
  var id2, timing;
  if (name instanceof Transition) {
    id2 = name._id, name = name._name;
  } else {
    id2 = newId(), (timing = defaultTiming).time = now(), name = name == null ? null : name + "";
  }
  for (var groups = this._groups, m = groups.length, j = 0; j < m; ++j) {
    for (var group = groups[j], n = group.length, node, i = 0; i < n; ++i) {
      if (node = group[i]) {
        schedule(node, name, id2, i, group, timing || inherit(node, id2));
      }
    }
  }
  return new Transition(groups, this._parents, name, id2);
}
selection.prototype.interrupt = selection_interrupt;
selection.prototype.transition = selection_transition;
const pi = Math.PI, tau = 2 * pi, epsilon = 1e-6, tauEpsilon = tau - epsilon;
function append(strings) {
  this._ += strings[0];
  for (let i = 1, n = strings.length; i < n; ++i) {
    this._ += arguments[i] + strings[i];
  }
}
function appendRound(digits) {
  let d = Math.floor(digits);
  if (!(d >= 0)) throw new Error(`invalid digits: ${digits}`);
  if (d > 15) return append;
  const k = 10 ** d;
  return function(strings) {
    this._ += strings[0];
    for (let i = 1, n = strings.length; i < n; ++i) {
      this._ += Math.round(arguments[i] * k) / k + strings[i];
    }
  };
}
class Path {
  constructor(digits) {
    this._x0 = this._y0 = // start of current subpath
    this._x1 = this._y1 = null;
    this._ = "";
    this._append = digits == null ? append : appendRound(digits);
  }
  moveTo(x2, y2) {
    this._append`M${this._x0 = this._x1 = +x2},${this._y0 = this._y1 = +y2}`;
  }
  closePath() {
    if (this._x1 !== null) {
      this._x1 = this._x0, this._y1 = this._y0;
      this._append`Z`;
    }
  }
  lineTo(x2, y2) {
    this._append`L${this._x1 = +x2},${this._y1 = +y2}`;
  }
  quadraticCurveTo(x1, y1, x2, y2) {
    this._append`Q${+x1},${+y1},${this._x1 = +x2},${this._y1 = +y2}`;
  }
  bezierCurveTo(x1, y1, x2, y2, x3, y3) {
    this._append`C${+x1},${+y1},${+x2},${+y2},${this._x1 = +x3},${this._y1 = +y3}`;
  }
  arcTo(x1, y1, x2, y2, r) {
    x1 = +x1, y1 = +y1, x2 = +x2, y2 = +y2, r = +r;
    if (r < 0) throw new Error(`negative radius: ${r}`);
    let x0 = this._x1, y0 = this._y1, x21 = x2 - x1, y21 = y2 - y1, x01 = x0 - x1, y01 = y0 - y1, l01_2 = x01 * x01 + y01 * y01;
    if (this._x1 === null) {
      this._append`M${this._x1 = x1},${this._y1 = y1}`;
    } else if (!(l01_2 > epsilon)) ;
    else if (!(Math.abs(y01 * x21 - y21 * x01) > epsilon) || !r) {
      this._append`L${this._x1 = x1},${this._y1 = y1}`;
    } else {
      let x20 = x2 - x0, y20 = y2 - y0, l21_2 = x21 * x21 + y21 * y21, l20_2 = x20 * x20 + y20 * y20, l21 = Math.sqrt(l21_2), l01 = Math.sqrt(l01_2), l = r * Math.tan((pi - Math.acos((l21_2 + l01_2 - l20_2) / (2 * l21 * l01))) / 2), t01 = l / l01, t21 = l / l21;
      if (Math.abs(t01 - 1) > epsilon) {
        this._append`L${x1 + t01 * x01},${y1 + t01 * y01}`;
      }
      this._append`A${r},${r},0,0,${+(y01 * x20 > x01 * y20)},${this._x1 = x1 + t21 * x21},${this._y1 = y1 + t21 * y21}`;
    }
  }
  arc(x2, y2, r, a0, a1, ccw) {
    x2 = +x2, y2 = +y2, r = +r, ccw = !!ccw;
    if (r < 0) throw new Error(`negative radius: ${r}`);
    let dx = r * Math.cos(a0), dy = r * Math.sin(a0), x0 = x2 + dx, y0 = y2 + dy, cw = 1 ^ ccw, da = ccw ? a0 - a1 : a1 - a0;
    if (this._x1 === null) {
      this._append`M${x0},${y0}`;
    } else if (Math.abs(this._x1 - x0) > epsilon || Math.abs(this._y1 - y0) > epsilon) {
      this._append`L${x0},${y0}`;
    }
    if (!r) return;
    if (da < 0) da = da % tau + tau;
    if (da > tauEpsilon) {
      this._append`A${r},${r},0,1,${cw},${x2 - dx},${y2 - dy}A${r},${r},0,1,${cw},${this._x1 = x0},${this._y1 = y0}`;
    } else if (da > epsilon) {
      this._append`A${r},${r},0,${+(da >= pi)},${cw},${this._x1 = x2 + r * Math.cos(a1)},${this._y1 = y2 + r * Math.sin(a1)}`;
    }
  }
  rect(x2, y2, w, h) {
    this._append`M${this._x0 = this._x1 = +x2},${this._y0 = this._y1 = +y2}h${w = +w}v${+h}h${-w}Z`;
  }
  toString() {
    return this._;
  }
}
function formatDecimal(x2) {
  return Math.abs(x2 = Math.round(x2)) >= 1e21 ? x2.toLocaleString("en").replace(/,/g, "") : x2.toString(10);
}
function formatDecimalParts(x2, p) {
  if ((i = (x2 = p ? x2.toExponential(p - 1) : x2.toExponential()).indexOf("e")) < 0) return null;
  var i, coefficient = x2.slice(0, i);
  return [
    coefficient.length > 1 ? coefficient[0] + coefficient.slice(2) : coefficient,
    +x2.slice(i + 1)
  ];
}
function exponent(x2) {
  return x2 = formatDecimalParts(Math.abs(x2)), x2 ? x2[1] : NaN;
}
function formatGroup(grouping, thousands) {
  return function(value, width) {
    var i = value.length, t = [], j = 0, g = grouping[0], length = 0;
    while (i > 0 && g > 0) {
      if (length + g + 1 > width) g = Math.max(1, width - length);
      t.push(value.substring(i -= g, i + g));
      if ((length += g + 1) > width) break;
      g = grouping[j = (j + 1) % grouping.length];
    }
    return t.reverse().join(thousands);
  };
}
function formatNumerals(numerals) {
  return function(value) {
    return value.replace(/[0-9]/g, function(i) {
      return numerals[+i];
    });
  };
}
var re = /^(?:(.)?([<>=^]))?([+\-( ])?([$#])?(0)?(\d+)?(,)?(\.\d+)?(~)?([a-z%])?$/i;
function formatSpecifier(specifier) {
  if (!(match = re.exec(specifier))) throw new Error("invalid format: " + specifier);
  var match;
  return new FormatSpecifier({
    fill: match[1],
    align: match[2],
    sign: match[3],
    symbol: match[4],
    zero: match[5],
    width: match[6],
    comma: match[7],
    precision: match[8] && match[8].slice(1),
    trim: match[9],
    type: match[10]
  });
}
formatSpecifier.prototype = FormatSpecifier.prototype;
function FormatSpecifier(specifier) {
  this.fill = specifier.fill === void 0 ? " " : specifier.fill + "";
  this.align = specifier.align === void 0 ? ">" : specifier.align + "";
  this.sign = specifier.sign === void 0 ? "-" : specifier.sign + "";
  this.symbol = specifier.symbol === void 0 ? "" : specifier.symbol + "";
  this.zero = !!specifier.zero;
  this.width = specifier.width === void 0 ? void 0 : +specifier.width;
  this.comma = !!specifier.comma;
  this.precision = specifier.precision === void 0 ? void 0 : +specifier.precision;
  this.trim = !!specifier.trim;
  this.type = specifier.type === void 0 ? "" : specifier.type + "";
}
FormatSpecifier.prototype.toString = function() {
  return this.fill + this.align + this.sign + this.symbol + (this.zero ? "0" : "") + (this.width === void 0 ? "" : Math.max(1, this.width | 0)) + (this.comma ? "," : "") + (this.precision === void 0 ? "" : "." + Math.max(0, this.precision | 0)) + (this.trim ? "~" : "") + this.type;
};
function formatTrim(s) {
  out: for (var n = s.length, i = 1, i0 = -1, i1; i < n; ++i) {
    switch (s[i]) {
      case ".":
        i0 = i1 = i;
        break;
      case "0":
        if (i0 === 0) i0 = i;
        i1 = i;
        break;
      default:
        if (!+s[i]) break out;
        if (i0 > 0) i0 = 0;
        break;
    }
  }
  return i0 > 0 ? s.slice(0, i0) + s.slice(i1 + 1) : s;
}
var prefixExponent;
function formatPrefixAuto(x2, p) {
  var d = formatDecimalParts(x2, p);
  if (!d) return x2 + "";
  var coefficient = d[0], exponent2 = d[1], i = exponent2 - (prefixExponent = Math.max(-8, Math.min(8, Math.floor(exponent2 / 3))) * 3) + 1, n = coefficient.length;
  return i === n ? coefficient : i > n ? coefficient + new Array(i - n + 1).join("0") : i > 0 ? coefficient.slice(0, i) + "." + coefficient.slice(i) : "0." + new Array(1 - i).join("0") + formatDecimalParts(x2, Math.max(0, p + i - 1))[0];
}
function formatRounded(x2, p) {
  var d = formatDecimalParts(x2, p);
  if (!d) return x2 + "";
  var coefficient = d[0], exponent2 = d[1];
  return exponent2 < 0 ? "0." + new Array(-exponent2).join("0") + coefficient : coefficient.length > exponent2 + 1 ? coefficient.slice(0, exponent2 + 1) + "." + coefficient.slice(exponent2 + 1) : coefficient + new Array(exponent2 - coefficient.length + 2).join("0");
}
var formatTypes = {
  "%": (x2, p) => (x2 * 100).toFixed(p),
  "b": (x2) => Math.round(x2).toString(2),
  "c": (x2) => x2 + "",
  "d": formatDecimal,
  "e": (x2, p) => x2.toExponential(p),
  "f": (x2, p) => x2.toFixed(p),
  "g": (x2, p) => x2.toPrecision(p),
  "o": (x2) => Math.round(x2).toString(8),
  "p": (x2, p) => formatRounded(x2 * 100, p),
  "r": formatRounded,
  "s": formatPrefixAuto,
  "X": (x2) => Math.round(x2).toString(16).toUpperCase(),
  "x": (x2) => Math.round(x2).toString(16)
};
function identity$1(x2) {
  return x2;
}
var map = Array.prototype.map, prefixes = ["y", "z", "a", "f", "p", "n", "µ", "m", "", "k", "M", "G", "T", "P", "E", "Z", "Y"];
function formatLocale(locale2) {
  var group = locale2.grouping === void 0 || locale2.thousands === void 0 ? identity$1 : formatGroup(map.call(locale2.grouping, Number), locale2.thousands + ""), currencyPrefix = locale2.currency === void 0 ? "" : locale2.currency[0] + "", currencySuffix = locale2.currency === void 0 ? "" : locale2.currency[1] + "", decimal = locale2.decimal === void 0 ? "." : locale2.decimal + "", numerals = locale2.numerals === void 0 ? identity$1 : formatNumerals(map.call(locale2.numerals, String)), percent = locale2.percent === void 0 ? "%" : locale2.percent + "", minus = locale2.minus === void 0 ? "−" : locale2.minus + "", nan = locale2.nan === void 0 ? "NaN" : locale2.nan + "";
  function newFormat(specifier) {
    specifier = formatSpecifier(specifier);
    var fill = specifier.fill, align = specifier.align, sign = specifier.sign, symbol = specifier.symbol, zero2 = specifier.zero, width = specifier.width, comma = specifier.comma, precision = specifier.precision, trim = specifier.trim, type = specifier.type;
    if (type === "n") comma = true, type = "g";
    else if (!formatTypes[type]) precision === void 0 && (precision = 12), trim = true, type = "g";
    if (zero2 || fill === "0" && align === "=") zero2 = true, fill = "0", align = "=";
    var prefix = symbol === "$" ? currencyPrefix : symbol === "#" && /[boxX]/.test(type) ? "0" + type.toLowerCase() : "", suffix = symbol === "$" ? currencySuffix : /[%p]/.test(type) ? percent : "";
    var formatType = formatTypes[type], maybeSuffix = /[defgprs%]/.test(type);
    precision = precision === void 0 ? 6 : /[gprs]/.test(type) ? Math.max(1, Math.min(21, precision)) : Math.max(0, Math.min(20, precision));
    function format2(value) {
      var valuePrefix = prefix, valueSuffix = suffix, i, n, c;
      if (type === "c") {
        valueSuffix = formatType(value) + valueSuffix;
        value = "";
      } else {
        value = +value;
        var valueNegative = value < 0 || 1 / value < 0;
        value = isNaN(value) ? nan : formatType(Math.abs(value), precision);
        if (trim) value = formatTrim(value);
        if (valueNegative && +value === 0 && sign !== "+") valueNegative = false;
        valuePrefix = (valueNegative ? sign === "(" ? sign : minus : sign === "-" || sign === "(" ? "" : sign) + valuePrefix;
        valueSuffix = (type === "s" ? prefixes[8 + prefixExponent / 3] : "") + valueSuffix + (valueNegative && sign === "(" ? ")" : "");
        if (maybeSuffix) {
          i = -1, n = value.length;
          while (++i < n) {
            if (c = value.charCodeAt(i), 48 > c || c > 57) {
              valueSuffix = (c === 46 ? decimal + value.slice(i + 1) : value.slice(i)) + valueSuffix;
              value = value.slice(0, i);
              break;
            }
          }
        }
      }
      if (comma && !zero2) value = group(value, Infinity);
      var length = valuePrefix.length + value.length + valueSuffix.length, padding = length < width ? new Array(width - length + 1).join(fill) : "";
      if (comma && zero2) value = group(padding + value, padding.length ? width - valueSuffix.length : Infinity), padding = "";
      switch (align) {
        case "<":
          value = valuePrefix + value + valueSuffix + padding;
          break;
        case "=":
          value = valuePrefix + padding + value + valueSuffix;
          break;
        case "^":
          value = padding.slice(0, length = padding.length >> 1) + valuePrefix + value + valueSuffix + padding.slice(length);
          break;
        default:
          value = padding + valuePrefix + value + valueSuffix;
          break;
      }
      return numerals(value);
    }
    format2.toString = function() {
      return specifier + "";
    };
    return format2;
  }
  function formatPrefix2(specifier, value) {
    var f = newFormat((specifier = formatSpecifier(specifier), specifier.type = "f", specifier)), e = Math.max(-8, Math.min(8, Math.floor(exponent(value) / 3))) * 3, k = Math.pow(10, -e), prefix = prefixes[8 + e / 3];
    return function(value2) {
      return f(k * value2) + prefix;
    };
  }
  return {
    format: newFormat,
    formatPrefix: formatPrefix2
  };
}
var locale;
var format;
var formatPrefix;
defaultLocale({
  thousands: ",",
  grouping: [3],
  currency: ["$", ""]
});
function defaultLocale(definition) {
  locale = formatLocale(definition);
  format = locale.format;
  formatPrefix = locale.formatPrefix;
  return locale;
}
function precisionFixed(step) {
  return Math.max(0, -exponent(Math.abs(step)));
}
function precisionPrefix(step, value) {
  return Math.max(0, Math.max(-8, Math.min(8, Math.floor(exponent(value) / 3))) * 3 - exponent(Math.abs(step)));
}
function precisionRound(step, max) {
  step = Math.abs(step), max = Math.abs(max) - step;
  return Math.max(0, exponent(max) - exponent(step)) + 1;
}
function initRange(domain, range) {
  switch (arguments.length) {
    case 0:
      break;
    case 1:
      this.range(domain);
      break;
    default:
      this.range(range).domain(domain);
      break;
  }
  return this;
}
function constants(x2) {
  return function() {
    return x2;
  };
}
function number(x2) {
  return +x2;
}
var unit = [0, 1];
function identity(x2) {
  return x2;
}
function normalize(a, b) {
  return (b -= a = +a) ? function(x2) {
    return (x2 - a) / b;
  } : constants(isNaN(b) ? NaN : 0.5);
}
function clamper(a, b) {
  var t;
  if (a > b) t = a, a = b, b = t;
  return function(x2) {
    return Math.max(a, Math.min(b, x2));
  };
}
function bimap(domain, range, interpolate2) {
  var d0 = domain[0], d1 = domain[1], r0 = range[0], r1 = range[1];
  if (d1 < d0) d0 = normalize(d1, d0), r0 = interpolate2(r1, r0);
  else d0 = normalize(d0, d1), r0 = interpolate2(r0, r1);
  return function(x2) {
    return r0(d0(x2));
  };
}
function polymap(domain, range, interpolate2) {
  var j = Math.min(domain.length, range.length) - 1, d = new Array(j), r = new Array(j), i = -1;
  if (domain[j] < domain[0]) {
    domain = domain.slice().reverse();
    range = range.slice().reverse();
  }
  while (++i < j) {
    d[i] = normalize(domain[i], domain[i + 1]);
    r[i] = interpolate2(range[i], range[i + 1]);
  }
  return function(x2) {
    var i2 = bisect(domain, x2, 1, j) - 1;
    return r[i2](d[i2](x2));
  };
}
function copy(source, target) {
  return target.domain(source.domain()).range(source.range()).interpolate(source.interpolate()).clamp(source.clamp()).unknown(source.unknown());
}
function transformer() {
  var domain = unit, range = unit, interpolate2 = interpolate$1, transform, untransform, unknown, clamp = identity, piecewise, output, input;
  function rescale() {
    var n = Math.min(domain.length, range.length);
    if (clamp !== identity) clamp = clamper(domain[0], domain[n - 1]);
    piecewise = n > 2 ? polymap : bimap;
    output = input = null;
    return scale;
  }
  function scale(x2) {
    return x2 == null || isNaN(x2 = +x2) ? unknown : (output || (output = piecewise(domain.map(transform), range, interpolate2)))(transform(clamp(x2)));
  }
  scale.invert = function(y2) {
    return clamp(untransform((input || (input = piecewise(range, domain.map(transform), interpolateNumber)))(y2)));
  };
  scale.domain = function(_2) {
    return arguments.length ? (domain = Array.from(_2, number), rescale()) : domain.slice();
  };
  scale.range = function(_2) {
    return arguments.length ? (range = Array.from(_2), rescale()) : range.slice();
  };
  scale.rangeRound = function(_2) {
    return range = Array.from(_2), interpolate2 = interpolateRound, rescale();
  };
  scale.clamp = function(_2) {
    return arguments.length ? (clamp = _2 ? true : identity, rescale()) : clamp !== identity;
  };
  scale.interpolate = function(_2) {
    return arguments.length ? (interpolate2 = _2, rescale()) : interpolate2;
  };
  scale.unknown = function(_2) {
    return arguments.length ? (unknown = _2, scale) : unknown;
  };
  return function(t, u) {
    transform = t, untransform = u;
    return rescale();
  };
}
function continuous() {
  return transformer()(identity, identity);
}
function tickFormat(start2, stop, count, specifier) {
  var step = tickStep(start2, stop, count), precision;
  specifier = formatSpecifier(specifier == null ? ",f" : specifier);
  switch (specifier.type) {
    case "s": {
      var value = Math.max(Math.abs(start2), Math.abs(stop));
      if (specifier.precision == null && !isNaN(precision = precisionPrefix(step, value))) specifier.precision = precision;
      return formatPrefix(specifier, value);
    }
    case "":
    case "e":
    case "g":
    case "p":
    case "r": {
      if (specifier.precision == null && !isNaN(precision = precisionRound(step, Math.max(Math.abs(start2), Math.abs(stop))))) specifier.precision = precision - (specifier.type === "e");
      break;
    }
    case "f":
    case "%": {
      if (specifier.precision == null && !isNaN(precision = precisionFixed(step))) specifier.precision = precision - (specifier.type === "%") * 2;
      break;
    }
  }
  return format(specifier);
}
function linearish(scale) {
  var domain = scale.domain;
  scale.ticks = function(count) {
    var d = domain();
    return ticks(d[0], d[d.length - 1], count == null ? 10 : count);
  };
  scale.tickFormat = function(count, specifier) {
    var d = domain();
    return tickFormat(d[0], d[d.length - 1], count == null ? 10 : count, specifier);
  };
  scale.nice = function(count) {
    if (count == null) count = 10;
    var d = domain();
    var i0 = 0;
    var i1 = d.length - 1;
    var start2 = d[i0];
    var stop = d[i1];
    var prestep;
    var step;
    var maxIter = 10;
    if (stop < start2) {
      step = start2, start2 = stop, stop = step;
      step = i0, i0 = i1, i1 = step;
    }
    while (maxIter-- > 0) {
      step = tickIncrement(start2, stop, count);
      if (step === prestep) {
        d[i0] = start2;
        d[i1] = stop;
        return domain(d);
      } else if (step > 0) {
        start2 = Math.floor(start2 / step) * step;
        stop = Math.ceil(stop / step) * step;
      } else if (step < 0) {
        start2 = Math.ceil(start2 * step) / step;
        stop = Math.floor(stop * step) / step;
      } else {
        break;
      }
      prestep = step;
    }
    return scale;
  };
  return scale;
}
function linear() {
  var scale = continuous();
  scale.copy = function() {
    return copy(scale, linear());
  };
  initRange.apply(scale, arguments);
  return linearish(scale);
}
function constant(x2) {
  return function constant2() {
    return x2;
  };
}
function withPath(shape) {
  let digits = 3;
  shape.digits = function(_2) {
    if (!arguments.length) return digits;
    if (_2 == null) {
      digits = null;
    } else {
      const d = Math.floor(_2);
      if (!(d >= 0)) throw new RangeError(`invalid digits: ${_2}`);
      digits = d;
    }
    return shape;
  };
  return () => new Path(digits);
}
function array(x2) {
  return typeof x2 === "object" && "length" in x2 ? x2 : Array.from(x2);
}
function Linear(context) {
  this._context = context;
}
Linear.prototype = {
  areaStart: function() {
    this._line = 0;
  },
  areaEnd: function() {
    this._line = NaN;
  },
  lineStart: function() {
    this._point = 0;
  },
  lineEnd: function() {
    if (this._line || this._line !== 0 && this._point === 1) this._context.closePath();
    this._line = 1 - this._line;
  },
  point: function(x2, y2) {
    x2 = +x2, y2 = +y2;
    switch (this._point) {
      case 0:
        this._point = 1;
        this._line ? this._context.lineTo(x2, y2) : this._context.moveTo(x2, y2);
        break;
      case 1:
        this._point = 2;
      // falls through
      default:
        this._context.lineTo(x2, y2);
        break;
    }
  }
};
function curveLinear(context) {
  return new Linear(context);
}
function x(p) {
  return p[0];
}
function y(p) {
  return p[1];
}
function line(x$1, y$1) {
  var defined = constant(true), context = null, curve = curveLinear, output = null, path = withPath(line2);
  x$1 = typeof x$1 === "function" ? x$1 : x$1 === void 0 ? x : constant(x$1);
  y$1 = typeof y$1 === "function" ? y$1 : y$1 === void 0 ? y : constant(y$1);
  function line2(data) {
    var i, n = (data = array(data)).length, d, defined0 = false, buffer;
    if (context == null) output = curve(buffer = path());
    for (i = 0; i <= n; ++i) {
      if (!(i < n && defined(d = data[i], i, data)) === defined0) {
        if (defined0 = !defined0) output.lineStart();
        else output.lineEnd();
      }
      if (defined0) output.point(+x$1(d, i, data), +y$1(d, i, data));
    }
    if (buffer) return output = null, buffer + "" || null;
  }
  line2.x = function(_2) {
    return arguments.length ? (x$1 = typeof _2 === "function" ? _2 : constant(+_2), line2) : x$1;
  };
  line2.y = function(_2) {
    return arguments.length ? (y$1 = typeof _2 === "function" ? _2 : constant(+_2), line2) : y$1;
  };
  line2.defined = function(_2) {
    return arguments.length ? (defined = typeof _2 === "function" ? _2 : constant(!!_2), line2) : defined;
  };
  line2.curve = function(_2) {
    return arguments.length ? (curve = _2, context != null && (output = curve(context)), line2) : curve;
  };
  line2.context = function(_2) {
    return arguments.length ? (_2 == null ? context = output = null : output = curve(context = _2), line2) : context;
  };
  return line2;
}
function Transform(k, x2, y2) {
  this.k = k;
  this.x = x2;
  this.y = y2;
}
Transform.prototype = {
  constructor: Transform,
  scale: function(k) {
    return k === 1 ? this : new Transform(this.k * k, this.x, this.y);
  },
  translate: function(x2, y2) {
    return x2 === 0 & y2 === 0 ? this : new Transform(this.k, this.x + this.k * x2, this.y + this.k * y2);
  },
  apply: function(point) {
    return [point[0] * this.k + this.x, point[1] * this.k + this.y];
  },
  applyX: function(x2) {
    return x2 * this.k + this.x;
  },
  applyY: function(y2) {
    return y2 * this.k + this.y;
  },
  invert: function(location) {
    return [(location[0] - this.x) / this.k, (location[1] - this.y) / this.k];
  },
  invertX: function(x2) {
    return (x2 - this.x) / this.k;
  },
  invertY: function(y2) {
    return (y2 - this.y) / this.k;
  },
  rescaleX: function(x2) {
    return x2.copy().domain(x2.range().map(this.invertX, this).map(x2.invert, x2));
  },
  rescaleY: function(y2) {
    return y2.copy().domain(y2.range().map(this.invertY, this).map(y2.invert, y2));
  },
  toString: function() {
    return "translate(" + this.x + "," + this.y + ") scale(" + this.k + ")";
  }
};
Transform.prototype;
var PreviewType;
(function(PreviewType2) {
  PreviewType2["Monomer"] = "monomer";
  PreviewType2["Preset"] = "preset";
  PreviewType2["Bond"] = "bond";
  PreviewType2["AmbiguousMonomer"] = "ambiguousMonomer";
})(PreviewType || (PreviewType = {}));
var PresetPosition;
(function(PresetPosition2) {
  PresetPosition2["Library"] = "library";
  PresetPosition2["ChainStart"] = "chainStart";
  PresetPosition2["ChainMiddle"] = "chainMiddle";
  PresetPosition2["ChainEnd"] = "chainEnd";
})(PresetPosition || (PresetPosition = {}));
var SELECT_SUBMENU_ID = "select-submenu";
var _T, _ref$1, _ref2, _;
function ownKeys$s(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$s(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$s(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$s(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var MolarMeasurementUnit;
(function(MolarMeasurementUnit2) {
  MolarMeasurementUnit2["nanoMol"] = "nM";
  MolarMeasurementUnit2["microMol"] = "μM";
  MolarMeasurementUnit2["milliMol"] = "mM";
})(MolarMeasurementUnit || (MolarMeasurementUnit = {}));
var molarMeasurementUnitToNumber = _defineProperty$1(_defineProperty$1(_defineProperty$1({}, MolarMeasurementUnit.nanoMol, Math.pow(10, 9)), MolarMeasurementUnit.microMol, Math.pow(10, 6)), MolarMeasurementUnit.milliMol, Math.pow(10, 3));
var initialState$3 = {
  ketcherId: "",
  isReady: null,
  activeTool: "select",
  editor: void 0,
  editorLayoutMode: void 0,
  editorLineLength: SettingsManager.editorLineLength,
  preview: {
    type: PreviewType.Monomer,
    monomer: void 0,
    style: {}
  },
  position: void 0,
  isContextMenuActive: false,
  isDragging: false,
  isMacromoleculesPropertiesWindowOpened: false,
  macromoleculesProperties: void 0,
  unipositiveIonsMeasurementUnit: MolarMeasurementUnit.milliMol,
  oligonucleotidesMeasurementUnit: MolarMeasurementUnit.microMol,
  unipositiveIonsValue: 140,
  oligonucleotidesValue: 200,
  app: {
    buildDate: (_T = "2026-07-13T14:43:16") !== null && _T !== void 0 ? _T : "",
    indigoVersion: (_ref$1 = "") !== null && _ref$1 !== void 0 ? _ref$1 : "",
    indigoMachine: (_ref2 = "") !== null && _ref2 !== void 0 ? _ref2 : "",
    version: (_ = "3.17.0") !== null && _ !== void 0 ? _ : ""
  },
  selectedMenuGroupItems: {}
};
var editorSlice = createSlice({
  name: "editor",
  initialState: initialState$3,
  reducers: {
    init: function init2(state) {
      state.isReady = false;
    },
    initKetcherId: function initKetcherId(state, action) {
      state.ketcherId = action.payload;
    },
    initSuccess: function initSuccess(state) {
      state.isReady = true;
    },
    initFailure: function initFailure(state) {
      state.isReady = false;
    },
    selectTool: function selectTool(state, action) {
      state.activeTool = action.payload;
    },
    setPosition: function setPosition(state, action) {
      state.position = action.payload;
    },
    createEditor: function createEditor(state, action) {
      var _action$payload$onIni, _action$payload;
      var editor = new CoreEditor({
        theme: action.payload.theme,
        canvas: action.payload.canvas,
        renderersContainer: new RenderersManager({
          theme: action.payload.theme
        })
      });
      editor.initializeMonomersLibraryFromKetcher(action.payload.monomersLibraryUpdate, action.payload.monomersLibraryReplace);
      state.editor = editor;
      (_action$payload$onIni = (_action$payload = action.payload).onInit) === null || _action$payload$onIni === void 0 || _action$payload$onIni.call(_action$payload, editor);
    },
    destroyEditor: function destroyEditor(state) {
      var _state$editor, _state$editor2;
      state.editorLayoutMode = (_state$editor = state.editor) === null || _state$editor === void 0 ? void 0 : _state$editor.mode.modeName;
      (_state$editor2 = state.editor) === null || _state$editor2 === void 0 || _state$editor2.destroy();
      state.editor = void 0;
    },
    showPreview: function showPreview(state, action) {
      state.preview = action.payload || {
        monomer: void 0,
        style: ""
      };
    },
    setContextMenuActive: function setContextMenuActive(state, action) {
      state.isContextMenuActive = action.payload;
    },
    setIsDragging: function setIsDragging(state, action) {
      state.isDragging = action.payload;
    },
    setMacromoleculesPropertiesWindowVisibility: function setMacromoleculesPropertiesWindowVisibility(state, action) {
      state.isMacromoleculesPropertiesWindowOpened = action.payload;
    },
    toggleMacromoleculesPropertiesWindowVisibility: function toggleMacromoleculesPropertiesWindowVisibility(state) {
      state.isMacromoleculesPropertiesWindowOpened = !state.isMacromoleculesPropertiesWindowOpened;
    },
    setMacromoleculesProperties: function setMacromoleculesProperties(state, action) {
      state.macromoleculesProperties = action.payload;
    },
    setUnipositiveIonsMeasurementUnit: function setUnipositiveIonsMeasurementUnit(state, action) {
      state.unipositiveIonsMeasurementUnit = action.payload;
    },
    setOligonucleotidesMeasurementUnit: function setOligonucleotidesMeasurementUnit(state, action) {
      state.oligonucleotidesMeasurementUnit = action.payload;
    },
    setEditorLineLength: function setEditorLineLength(state, action) {
      state.editorLineLength = _objectSpread$s(_objectSpread$s({}, state.editorLineLength), action.payload);
    },
    setUnipositiveIonsValue: function setUnipositiveIonsValue(state, action) {
      state.unipositiveIonsValue = action.payload;
    },
    setOligonucleotidesValue: function setOligonucleotidesValue(state, action) {
      state.oligonucleotidesValue = action.payload;
    },
    setAppMeta: function setAppMeta(state, action) {
      state.app = action.payload;
    },
    setSelectedMenuGroupItem: function setSelectedMenuGroupItem(state, action) {
      state.selectedMenuGroupItems = _objectSpread$s(_objectSpread$s({}, state.selectedMenuGroupItems), {}, _defineProperty$1({}, action.payload.groupName, action.payload.activeItemName));
    }
  }
});
var _editorSlice$actions = editorSlice.actions;
_editorSlice$actions.init;
_editorSlice$actions.initSuccess;
_editorSlice$actions.initFailure;
var initKetcherId2 = _editorSlice$actions.initKetcherId, selectTool2 = _editorSlice$actions.selectTool;
_editorSlice$actions.setPosition;
var createEditor2 = _editorSlice$actions.createEditor, destroyEditor2 = _editorSlice$actions.destroyEditor, showPreview2 = _editorSlice$actions.showPreview, setContextMenuActive2 = _editorSlice$actions.setContextMenuActive, setIsDragging2 = _editorSlice$actions.setIsDragging, setMacromoleculesPropertiesWindowVisibility2 = _editorSlice$actions.setMacromoleculesPropertiesWindowVisibility, toggleMacromoleculesPropertiesWindowVisibility2 = _editorSlice$actions.toggleMacromoleculesPropertiesWindowVisibility, setMacromoleculesProperties2 = _editorSlice$actions.setMacromoleculesProperties, setUnipositiveIonsMeasurementUnit2 = _editorSlice$actions.setUnipositiveIonsMeasurementUnit, setOligonucleotidesMeasurementUnit2 = _editorSlice$actions.setOligonucleotidesMeasurementUnit, setEditorLineLength2 = _editorSlice$actions.setEditorLineLength, setUnipositiveIonsValue2 = _editorSlice$actions.setUnipositiveIonsValue, setOligonucleotidesValue2 = _editorSlice$actions.setOligonucleotidesValue, setAppMeta2 = _editorSlice$actions.setAppMeta, setSelectedMenuGroupItem2 = _editorSlice$actions.setSelectedMenuGroupItem;
var selectShowPreview = function selectShowPreview2(state) {
  return state.editor.preview;
};
var selectEditorActiveTool = function selectEditorActiveTool2(state) {
  return state.editor.activeTool;
};
var selectKetcherId = function selectKetcherId2(state) {
  return state.editor.ketcherId;
};
var selectEditor = function selectEditor2(state) {
  return state.editor.editor;
};
var selectIsSequenceEditInRNABuilderMode = function selectIsSequenceEditInRNABuilderMode2(state) {
  var _state$editor$editor;
  return (_state$editor$editor = state.editor.editor) === null || _state$editor$editor === void 0 ? void 0 : _state$editor$editor.isSequenceEditInRNABuilderMode;
};
var selectIsSequenceMode = function selectIsSequenceMode2(state) {
  var _state$editor$editor2;
  return (_state$editor$editor2 = state.editor.editor) === null || _state$editor$editor2 === void 0 ? void 0 : _state$editor$editor2.isSequenceMode;
};
var selectEditorLayoutMode = function selectEditorLayoutMode2(state) {
  return state.editor.editorLayoutMode;
};
var selectIsHandToolSelected = function selectIsHandToolSelected2(state) {
  var _state$editor$editor4;
  return (_state$editor$editor4 = state.editor.editor) === null || _state$editor$editor4 === void 0 ? void 0 : _state$editor$editor4.isHandToolSelected;
};
var hasAntisenseChains = function hasAntisenseChains2(state) {
  var _state$editor$editor5;
  return (_state$editor$editor5 = state.editor.editor) === null || _state$editor$editor5 === void 0 || (_state$editor$editor5 = _state$editor$editor5.drawingEntitiesManager) === null || _state$editor$editor5 === void 0 ? void 0 : _state$editor$editor5.hasAntisenseChains;
};
var selectIsContextMenuActive = function selectIsContextMenuActive2(state) {
  return state.editor.isContextMenuActive;
};
var selectIsDragging = function selectIsDragging2(state) {
  return state.editor.isDragging;
};
var selectIsMacromoleculesPropertiesWindowOpened = function selectIsMacromoleculesPropertiesWindowOpened2(state) {
  return state.editor.isMacromoleculesPropertiesWindowOpened;
};
var selectMacromoleculesProperties = function selectMacromoleculesProperties2(state) {
  return state.editor.macromoleculesProperties;
};
var selectUnipositiveIonsMeasurementUnit = function selectUnipositiveIonsMeasurementUnit2(state) {
  return state.editor.unipositiveIonsMeasurementUnit;
};
var selectOligonucleotidesMeasurementUnit = function selectOligonucleotidesMeasurementUnit2(state) {
  return state.editor.oligonucleotidesMeasurementUnit;
};
var selectUnipositiveIonsValue = function selectUnipositiveIonsValue2(state) {
  return state.editor.unipositiveIonsValue;
};
var selectOligonucleotidesValue = function selectOligonucleotidesValue2(state) {
  return state.editor.oligonucleotidesValue;
};
var selectEditorLineLength = function selectEditorLineLength2(state) {
  return state.editor.editorLineLength;
};
var selectAppMeta = function selectAppMeta2(state) {
  return state.editor.app;
};
var selectSelectedMenuGroupItem = function selectSelectedMenuGroupItem2(groupItemName) {
  return function(state) {
    return state.editor.selectedMenuGroupItems[groupItemName];
  };
};
var selectLastSelectedSelectionMenuItem = function selectLastSelectedSelectionMenuItem2(state) {
  return state.editor.selectedMenuGroupItems[SELECT_SUBMENU_ID] || "select-rectangle";
};
var editorReducer = editorSlice.reducer;
var MONOMER_LIBRARY_FAVORITES = "FAVORITES";
var MONOMER_LIBRARY_PEPTIDES = "PEPTIDE";
var MONOMER_TYPES = {
  PEPTIDE: "PEPTIDE",
  CHEM: "CHEM",
  RNA: "RNA"
};
var MonomerGroups;
(function(MonomerGroups2) {
  MonomerGroups2["SUGARS"] = "Sugars";
  MonomerGroups2["BASES"] = "Bases";
  MonomerGroups2["PHOSPHATES"] = "Phosphates";
  MonomerGroups2["PEPTIDES"] = "Amino Acids";
  MonomerGroups2["NUCLEOTIDES"] = "Nucleotides";
})(MonomerGroups || (MonomerGroups = {}));
var MonomerGroupCodes;
(function(MonomerGroupCodes2) {
  MonomerGroupCodes2["R"] = "R";
  MonomerGroupCodes2["A"] = "A";
  MonomerGroupCodes2["C"] = "C";
  MonomerGroupCodes2["G"] = "G";
  MonomerGroupCodes2["T"] = "T";
  MonomerGroupCodes2["U"] = "U";
  MonomerGroupCodes2["X"] = "X";
  MonomerGroupCodes2["P"] = "P";
})(MonomerGroupCodes || (MonomerGroupCodes = {}));
({
  R: MonomerGroups.SUGARS,
  A: MonomerGroups.BASES,
  C: MonomerGroups.BASES,
  G: MonomerGroups.BASES,
  T: MonomerGroups.BASES,
  U: MonomerGroups.BASES,
  X: MonomerGroups.BASES,
  P: MonomerGroups.PHOSPHATES
});
var FAVORITE_ITEMS_UNIQUE_KEYS = "favoriteItemsUniqueKeys";
var CUSTOM_PRESETS = "ketcher_custom_presets";
var PRESET_PHOSPHATE_FILTER_STORAGE_KEY = "ketcher_preset_phosphate_filter";
var NoNaturalAnalogueGroupCode = "Z";
var NoNaturalAnalogueGroupTitle = "No natural analogue";
var DNA_TEMPLATE_NAME_PART$1 = "thymine";
var RNA_TEMPLATE_NAME_PART$1 = "uracil";
var LIBRARY_TAB_INDEX = {
  PEPTIDES: 1,
  RNA: 2};
var FavoriteStarSymbol = "★";
var LocalStorageWrapper = (function() {
  function LocalStorageWrapper2() {
    _classCallCheck(this, LocalStorageWrapper2);
    this.localStorage = window.localStorage;
  }
  _createClass(LocalStorageWrapper2, [{
    key: "getItem",
    value: function getItem(key) {
      var item = this.localStorage.getItem(key);
      if (!item) {
        return null;
      }
      return JSON.parse(item);
    }
  }, {
    key: "setItem",
    value: function setItem(key, item) {
      this.localStorage.setItem(key, JSON.stringify(item));
    }
  }, {
    key: "removeItem",
    value: function removeItem(key) {
      this.localStorage.removeItem(key);
    }
  }]);
  return LocalStorageWrapper2;
})();
var localStorageWrapper = new LocalStorageWrapper();
function ownKeys$r(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$r(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$r(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$r(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var LIBRARY_GROUP_NAME_TO_MONOMER_CLASS = _defineProperty$1(_defineProperty$1({}, MonomerGroups$1.PEPTIDES, KetMonomerClass.AminoAcid), MonomerGroups$1.BASES, KetMonomerClass.Base);
var initialState$2 = {
  monomers: [],
  defaultRnaPresets: [],
  favorites: {},
  searchFilter: "",
  selectedTabIndex: LIBRARY_TAB_INDEX.RNA
};
function getMonomerUniqueKey(monomer) {
  var _monomer$props;
  return isAmbiguousMonomerLibraryItem(monomer) ? monomer.id || monomer.label : "".concat(monomer.props.MonomerName, "___").concat((_monomer$props = monomer.props) === null || _monomer$props === void 0 ? void 0 : _monomer$props.Name);
}
function getPresetUniqueKey(preset) {
  var _preset$base$label, _preset$base, _preset$sugar$label, _preset$sugar, _preset$phosphate$lab, _preset$phosphate;
  return "".concat(preset.name, "_").concat((_preset$base$label = (_preset$base = preset.base) === null || _preset$base === void 0 ? void 0 : _preset$base.label) !== null && _preset$base$label !== void 0 ? _preset$base$label : ".", "_").concat((_preset$sugar$label = (_preset$sugar = preset.sugar) === null || _preset$sugar === void 0 ? void 0 : _preset$sugar.label) !== null && _preset$sugar$label !== void 0 ? _preset$sugar$label : ".", "_").concat((_preset$phosphate$lab = (_preset$phosphate = preset.phosphate) === null || _preset$phosphate === void 0 ? void 0 : _preset$phosphate.label) !== null && _preset$phosphate$lab !== void 0 ? _preset$phosphate$lab : ".");
}
var librarySlice = createSlice({
  name: "library",
  initialState: initialState$2,
  reducers: {
    loadMonomerLibrary: function loadMonomerLibrary(state, action) {
      var clonedMonomers = action.payload.map(function(monomer) {
        return _objectSpread$r(_objectSpread$r({}, monomer), {}, {
          props: _objectSpread$r({}, monomer.props)
        });
      });
      state.monomers = clonedMonomers;
    },
    loadDefaultPresets: function loadDefaultPresets(state, action) {
      state.defaultRnaPresets = action.payload.map(function(groupTemplate) {
        return _objectSpread$r({}, groupTemplate);
      });
    },
    setFavoriteMonomersFromLocalStorage: function setFavoriteMonomersFromLocalStorage(state) {
      var localFavorites = {};
      var favoritesInLocalStorage = localStorageWrapper.getItem(FAVORITE_ITEMS_UNIQUE_KEYS);
      if (!favoritesInLocalStorage || !Array.isArray(favoritesInLocalStorage)) {
        return;
      }
      state.monomers.forEach(function(monomer) {
        var uniqueKey = getMonomerUniqueKey(monomer);
        var favoriteItem = favoritesInLocalStorage.find(function(key) {
          return key === uniqueKey;
        });
        if (!favoriteItem) {
          return;
        }
        localFavorites[uniqueKey] = _objectSpread$r(_objectSpread$r({}, monomer), {}, {
          favorite: true
        });
      });
      state.favorites = localFavorites;
    },
    clearFavorites: function clearFavorites(state) {
      state.favorites = {};
    },
    toggleMonomerFavorites: function toggleMonomerFavorites(state, action) {
      var _localStorageWrapper$;
      var key = getMonomerUniqueKey(action.payload);
      var favoriteItemsUniqueKeys = (_localStorageWrapper$ = localStorageWrapper.getItem(FAVORITE_ITEMS_UNIQUE_KEYS)) !== null && _localStorageWrapper$ !== void 0 ? _localStorageWrapper$ : [];
      if (state.favorites[key]) {
        delete state.favorites[key];
        localStorageWrapper.setItem(FAVORITE_ITEMS_UNIQUE_KEYS, favoriteItemsUniqueKeys.filter(function(targetKey) {
          return targetKey !== key;
        }));
      } else {
        state.favorites[key] = _objectSpread$r(_objectSpread$r({}, action.payload), {}, {
          favorite: true
        });
        favoriteItemsUniqueKeys.push(key);
        localStorageWrapper.setItem(FAVORITE_ITEMS_UNIQUE_KEYS, favoriteItemsUniqueKeys);
      }
    },
    setSearchFilter: function setSearchFilter(state, action) {
      state.searchFilter = action.payload;
    },
    setSelectedTabIndex: function setSelectedTabIndex(state, action) {
      state.selectedTabIndex = action.payload;
    }
  }
});
var _librarySlice$actions = librarySlice.actions, loadMonomerLibrary2 = _librarySlice$actions.loadMonomerLibrary, loadDefaultPresets2 = _librarySlice$actions.loadDefaultPresets, setFavoriteMonomersFromLocalStorage2 = _librarySlice$actions.setFavoriteMonomersFromLocalStorage;
_librarySlice$actions.clearFavorites;
var toggleMonomerFavorites2 = _librarySlice$actions.toggleMonomerFavorites, setSearchFilter2 = _librarySlice$actions.setSearchFilter, setSelectedTabIndex2 = _librarySlice$actions.setSelectedTabIndex;
var selectAxoLabsAliasesByPresetName = createSelector(function(state) {
  return state.library.defaultRnaPresets;
}, function(defaultPresets) {
  var presets = defaultPresets !== null && defaultPresets !== void 0 ? defaultPresets : [];
  return presets.reduce(function(aliases, preset) {
    if (preset.aliasAxoLabs && preset.name) {
      aliases.set(preset.name.toLowerCase(), preset.aliasAxoLabs.toLowerCase());
    }
    return aliases;
  }, /* @__PURE__ */ new Map());
});
var selectSearchFilter = function selectSearchFilter2(state) {
  return state.library.searchFilter;
};
var selectMonomersInCategory = function selectMonomersInCategory2(items, category) {
  return items.filter(function(item) {
    var _item$props;
    return !item.isAmbiguous && ((_item$props = item.props) === null || _item$props === void 0 ? void 0 : _item$props.MonomerType) === category;
  });
};
var selectAmbiguousMonomersInCategory = function selectAmbiguousMonomersInCategory2(libraryItems, libraryGroupName) {
  var ambiguousMonomerLibraryItems = libraryItems.filter(function(libraryItem) {
    if (!isAmbiguousMonomerLibraryItem(libraryItem)) {
      return false;
    }
    var ambiguousMonomer = new AmbiguousMonomer(libraryItem, void 0, false);
    return LIBRARY_GROUP_NAME_TO_MONOMER_CLASS[libraryGroupName] === ambiguousMonomer.monomerClass;
  });
  if (ambiguousMonomerLibraryItems.length === 0) {
    return [];
  }
  var groupedAmbiguousMonomerLibraryItems = [];
  if (libraryGroupName === MonomerGroups$1.BASES) {
    groupedAmbiguousMonomerLibraryItems = [{
      groupTitle: "Ambiguous Bases",
      groupItems: ambiguousMonomerLibraryItems.filter(function(libraryItem) {
        return isAmbiguousMonomerLibraryItem(libraryItem) && libraryItem.options.every(function(option) {
          return !option.templateId.toLowerCase().includes(DNA_TEMPLATE_NAME_PART$1) && !option.templateId.toLowerCase().includes(RNA_TEMPLATE_NAME_PART$1);
        });
      })
    }, {
      groupTitle: "Ambiguous DNA Bases",
      groupItems: ambiguousMonomerLibraryItems.filter(function(libraryItem) {
        return isAmbiguousMonomerLibraryItem(libraryItem) && libraryItem.options.find(function(option) {
          return option.templateId.toLowerCase().includes(DNA_TEMPLATE_NAME_PART$1);
        });
      })
    }, {
      groupTitle: "Ambiguous RNA Bases",
      groupItems: ambiguousMonomerLibraryItems.filter(function(libraryItem) {
        return isAmbiguousMonomerLibraryItem(libraryItem) && libraryItem.options.find(function(option) {
          return option.templateId.toLowerCase().includes(RNA_TEMPLATE_NAME_PART$1);
        });
      })
    }];
  } else {
    groupedAmbiguousMonomerLibraryItems.push({
      groupTitle: "Ambiguous ".concat(libraryGroupName),
      groupItems: ambiguousMonomerLibraryItems
    });
  }
  var firstAmbiguousMonomersInLibrary = ["X", "N"];
  groupedAmbiguousMonomerLibraryItems.forEach(function(group) {
    group.groupItems.sort(function(ambiguousMonomerLibraryItem, ambiguousMonomerLibraryItemToCompare) {
      return ambiguousMonomerLibraryItem.label.localeCompare(ambiguousMonomerLibraryItemToCompare.label);
    });
    group.groupItems.sort(function(ambiguousMonomerLibraryItem) {
      return firstAmbiguousMonomersInLibrary.includes(ambiguousMonomerLibraryItem.label) ? -1 : 1;
    });
  });
  return groupedAmbiguousMonomerLibraryItems;
};
var selectUnsplitNucleotides = function selectUnsplitNucleotides2(items) {
  return items.filter(function(item) {
    var _item$props2, _item$props3;
    return !item.isAmbiguous && (((_item$props2 = item.props) === null || _item$props2 === void 0 ? void 0 : _item$props2.MonomerClass) === KetMonomerClass.RNA || ((_item$props3 = item.props) === null || _item$props3 === void 0 ? void 0 : _item$props3.MonomerClass) === KetMonomerClass.DNA);
  });
};
var selectMonomersInFavorites = function selectMonomersInFavorites2(items) {
  return items.filter(function(item) {
    return item.favorite && !item.isAmbiguous;
  });
};
var selectAmbiguousMonomersInFavorites = function selectAmbiguousMonomersInFavorites2(items) {
  var favoritesAmbiguousMonomers = [];
  for (var groupName in MonomerGroups$1) {
    var ambiguousMonomers = selectAmbiguousMonomersInCategory(items, MonomerGroups$1[groupName]);
    favoritesAmbiguousMonomers = [].concat(_toConsumableArray(favoritesAmbiguousMonomers), _toConsumableArray(ambiguousMonomers));
  }
  favoritesAmbiguousMonomers.forEach(function(group) {
    group.groupItems = group.groupItems.filter(function(item) {
      return item.favorite;
    });
  });
  return favoritesAmbiguousMonomers.filter(function(group) {
    return group.groupItems.length;
  });
};
var selectFilteredMonomers = createSelector(function(state) {
  return state.library;
}, function(state) {
  var searchFilter = state.searchFilter, monomers = state.monomers, favorites = state.favorites;
  var normalizedSearchFilter = searchFilter.toLowerCase();
  var checkMonomerMatch = function checkMonomerMatch2(idtAliases, searchFilter2) {
    var _idtAliases$base, _helmAlias$toLowerCas, _bilnAlias$toLowerCas, _axoLabsAlias$toLower;
    var name = arguments.length > 2 && arguments[2] !== void 0 ? arguments[2] : "";
    var fullName = arguments.length > 3 && arguments[3] !== void 0 ? arguments[3] : "";
    var helmAlias = arguments.length > 4 && arguments[4] !== void 0 ? arguments[4] : "";
    var bilnAlias = arguments.length > 5 && arguments[5] !== void 0 ? arguments[5] : "";
    var axoLabsAlias = arguments.length > 6 && arguments[6] !== void 0 ? arguments[6] : "";
    var modificationTypes = arguments.length > 7 && arguments[7] !== void 0 ? arguments[7] : [];
    var monomerName = name.toLowerCase();
    var monomerNameFull = fullName.toLowerCase();
    var idtBase = idtAliases === null || idtAliases === void 0 || (_idtAliases$base = idtAliases.base) === null || _idtAliases$base === void 0 ? void 0 : _idtAliases$base.toLowerCase();
    var idtModifications = idtAliases !== null && idtAliases !== void 0 && idtAliases.modifications ? Object.values(idtAliases.modifications).map(function(mod) {
      return mod.toLowerCase();
    }).join(" ") : "";
    var helmAliasLower = (_helmAlias$toLowerCas = helmAlias === null || helmAlias === void 0 ? void 0 : helmAlias.toLowerCase()) !== null && _helmAlias$toLowerCas !== void 0 ? _helmAlias$toLowerCas : "";
    var bilnAliasLower = (_bilnAlias$toLowerCas = bilnAlias === null || bilnAlias === void 0 ? void 0 : bilnAlias.toLowerCase()) !== null && _bilnAlias$toLowerCas !== void 0 ? _bilnAlias$toLowerCas : "";
    var axoLabsAliasLower = (_axoLabsAlias$toLower = axoLabsAlias === null || axoLabsAlias === void 0 ? void 0 : axoLabsAlias.toLowerCase()) !== null && _axoLabsAlias$toLower !== void 0 ? _axoLabsAlias$toLower : "";
    var modificationTypesLower = modificationTypes && modificationTypes.length > 0 ? modificationTypes.map(function(type) {
      return type.toLowerCase();
    }).join(" ") : "";
    if (searchFilter2 === "/") {
      return Boolean(idtBase || idtModifications);
    }
    if (searchFilter2.includes("/")) {
      var parts = searchFilter2.split("/");
      if (parts.length > 3 || parts.length === 3 && parts[2] !== "") {
        return false;
      }
      if (parts.length === 3 && parts[1] !== "") {
        var textBetweenSlashes = parts[1];
        var _matchesIdtBase = (idtBase === null || idtBase === void 0 ? void 0 : idtBase.length) === textBetweenSlashes.length && Array.from(idtBase).every(function(_char, index) {
          return _char === textBetweenSlashes[index];
        });
        var _matchesIdtModifications = idtModifications ? idtModifications.split(" ").some(function(mod) {
          return mod.length === textBetweenSlashes.length && Array.from(mod).every(function(_char2, index) {
            return _char2 === textBetweenSlashes[index];
          });
        }) : false;
        return _matchesIdtBase || _matchesIdtModifications;
      }
      var searchBeforeSlash = parts[0];
      var searchAfterSlash = parts[1];
      if (searchFilter2.startsWith("/") && searchFilter2.length > 1) {
        var aliasRest = searchFilter2.slice(1);
        return (idtBase === null || idtBase === void 0 ? void 0 : idtBase.startsWith(aliasRest)) || (idtModifications === null || idtModifications === void 0 ? void 0 : idtModifications.split(" ").some(function(mod) {
          return mod.startsWith(aliasRest);
        }));
      }
      if (searchFilter2.endsWith("/") && searchFilter2.length > 1) {
        var _aliasRest = searchFilter2.slice(0, -1);
        return (idtBase === null || idtBase === void 0 ? void 0 : idtBase.endsWith(_aliasRest)) || (idtModifications === null || idtModifications === void 0 ? void 0 : idtModifications.split(" ").some(function(mod) {
          return mod.endsWith(_aliasRest);
        }));
      }
      var _matchesIdtBase2 = (idtBase === null || idtBase === void 0 ? void 0 : idtBase.startsWith(searchAfterSlash)) && (idtBase === null || idtBase === void 0 ? void 0 : idtBase.endsWith(searchBeforeSlash));
      var _matchesIdtModifications2 = idtModifications ? idtModifications.split(" ").some(function(mod) {
        return mod.startsWith(searchAfterSlash) && mod.endsWith(searchBeforeSlash);
      }) : false;
      return _matchesIdtBase2 || _matchesIdtModifications2;
    }
    var matchesIdtBase = idtBase ? idtBase.includes(searchFilter2) : false;
    var matchesIdtModifications = idtModifications ? idtModifications.includes(searchFilter2) : false;
    var matchesHelmAlias = helmAliasLower ? helmAliasLower.includes(searchFilter2) : false;
    var matchesBilnAlias = bilnAliasLower ? bilnAliasLower.includes(searchFilter2) : false;
    var matchesAxoLabsAlias = axoLabsAliasLower ? axoLabsAliasLower.includes(searchFilter2) : false;
    var matchesModificationTypes = modificationTypesLower ? modificationTypesLower.includes(searchFilter2) : false;
    var cond = monomerName.includes(searchFilter2) || monomerNameFull.includes(searchFilter2) || matchesIdtBase || matchesIdtModifications || matchesHelmAlias || matchesBilnAlias || matchesAxoLabsAlias || matchesModificationTypes;
    return cond;
  };
  return monomers.filter(function(item) {
    var _item$props4;
    if (!item.isAmbiguous && (_item$props4 = item.props) !== null && _item$props4 !== void 0 && _item$props4.hidden) {
      return false;
    }
    if (item.isAmbiguous) {
      var label = item.label, id2 = item.id, idtAliases = item.idtAliases, components = item.monomers;
      var matchesMonomer = checkMonomerMatch(idtAliases, normalizedSearchFilter, label, id2);
      return matchesMonomer || components.some(function(monomer) {
        var _monomer$monomerItem$ = monomer.monomerItem.props, Name2 = _monomer$monomerItem$.Name, MonomerName3 = _monomer$monomerItem$.MonomerName, idtAliases2 = _monomer$monomerItem$.idtAliases, aliasHELM2 = _monomer$monomerItem$.aliasHELM, aliasBILN2 = _monomer$monomerItem$.aliasBILN, aliasAxoLabs2 = _monomer$monomerItem$.aliasAxoLabs, modificationTypes2 = _monomer$monomerItem$.modificationTypes;
        return checkMonomerMatch(idtAliases2, normalizedSearchFilter, Name2, MonomerName3, aliasHELM2, aliasBILN2, aliasAxoLabs2, modificationTypes2);
      });
    } else {
      var _item$props5 = item.props, Name = _item$props5.Name, MonomerName2 = _item$props5.MonomerName, _idtAliases = _item$props5.idtAliases, aliasHELM = _item$props5.aliasHELM, aliasBILN = _item$props5.aliasBILN, aliasAxoLabs = _item$props5.aliasAxoLabs, modificationTypes = _item$props5.modificationTypes;
      return checkMonomerMatch(_idtAliases, normalizedSearchFilter, Name, MonomerName2, aliasHELM, aliasBILN, aliasAxoLabs, modificationTypes);
    }
  }).map(function(item) {
    return _objectSpread$r(_objectSpread$r({}, item), {}, {
      favorite: !!favorites[getMonomerUniqueKey(item)]
    });
  });
});
var selectMonomerGroups = function selectMonomerGroups2(monomers) {
  var preparedData = monomers.reduce(function(result, monomerItem) {
    var code = monomerItem.props.MonomerNaturalAnalogCode || NoNaturalAnalogueGroupCode;
    if (!result[code]) {
      result[code] = [];
    }
    result[code].push(_objectSpread$r(_objectSpread$r({}, monomerItem), {}, {
      label: monomerItem.props.MonomerName
    }));
    return result;
  }, {});
  var sortedPreparedData = Object.entries(preparedData).reduce(function(result, _ref3) {
    var _ref22 = _slicedToArray(_ref3, 2), code = _ref22[0], monomers2 = _ref22[1];
    var sortedMonomers = _toConsumableArray(monomers2);
    sortedMonomers.sort(function(a, b) {
      return a.label.localeCompare(b.label);
    });
    var baseIndex = sortedMonomers.findIndex(function(monomer) {
      return monomer.label === code;
    });
    if (baseIndex !== -1) {
      var base = sortedMonomers.splice(baseIndex, 1);
      sortedMonomers.unshift(base[0]);
    }
    result[code] = sortedMonomers;
    return result;
  }, {});
  var preparedGroups = [];
  var sortedGroupCodes = Object.keys(sortedPreparedData);
  sortedGroupCodes.sort(function(a, b) {
    return a.localeCompare(b);
  });
  return sortedGroupCodes.reduce(function(result, code) {
    var group = {
      groupTitle: code === NoNaturalAnalogueGroupCode ? NoNaturalAnalogueGroupTitle : code,
      groupItems: []
    };
    sortedPreparedData[code].forEach(function(item) {
      group.groupItems.push(_objectSpread$r(_objectSpread$r({}, item), {}, {
        props: _objectSpread$r({}, item.props)
      }));
    });
    if (group.groupItems.length) {
      result.push(group);
    }
    return result;
  }, preparedGroups);
};
var selectCurrentTabIndex = function selectCurrentTabIndex2(state) {
  return state.library.selectedTabIndex;
};
var libraryReducer = librarySlice.reducer;
var selectDefaultRnaPresets = function selectDefaultRnaPresets2(state) {
  return state.library.defaultRnaPresets;
};
var initialState$1 = {
  name: null,
  isOpen: false,
  additionalProps: null,
  errorTooltips: [],
  errorModalText: "",
  errorModalTitle: ""
};
var modalSlice = createSlice({
  name: "modal",
  initialState: initialState$1,
  reducers: {
    openModal: function openModal(state, action) {
      if (typeof action.payload === "string") {
        state.name = action.payload;
      } else {
        state.name = action.payload.name;
        state.additionalProps = action.payload.additionalProps;
      }
      state.isOpen = true;
    },
    closeModal: function closeModal(state) {
      state.name = null;
      state.isOpen = false;
      state.additionalProps = null;
    },
    openErrorTooltip: function openErrorTooltip(state, action) {
      if (!state.errorTooltips.includes(action.payload)) {
        state.errorTooltips.push(action.payload);
      }
    },
    closeErrorTooltip: function closeErrorTooltip(state, action) {
      state.errorTooltips = action.payload ? state.errorTooltips.filter(function(text) {
        return text !== action.payload;
      }) : [];
    },
    openErrorModal: function openErrorModal(state, action) {
      if (typeof action.payload === "string") {
        state.errorModalText = action.payload;
      } else {
        var _action$payload = action.payload, errorMessage = _action$payload.errorMessage, errorTitle = _action$payload.errorTitle;
        state.errorModalText = errorMessage;
        state.errorModalTitle = errorTitle;
      }
    },
    closeErrorModal: function closeErrorModal(state) {
      state.errorModalText = "";
    }
  }
});
var _modalSlice$actions = modalSlice.actions, openModal2 = _modalSlice$actions.openModal, closeModal2 = _modalSlice$actions.closeModal, openErrorTooltip2 = _modalSlice$actions.openErrorTooltip, closeErrorTooltip2 = _modalSlice$actions.closeErrorTooltip, openErrorModal2 = _modalSlice$actions.openErrorModal, closeErrorModal2 = _modalSlice$actions.closeErrorModal;
var selectModalName = function selectModalName2(state) {
  return state.modal.name;
};
var selectModalIsOpen = function selectModalIsOpen2(state) {
  return state.modal.isOpen;
};
var selectAdditionalProps = function selectAdditionalProps2(state) {
  return state.modal.additionalProps;
};
var selectErrorTooltips = function selectErrorTooltips2(state) {
  return state.modal.errorTooltips;
};
var selectErrorModalText = function selectErrorModalText2(state) {
  return state.modal.errorModalText;
};
var selectErrorModalTitle = function selectErrorModalTitle2(state) {
  return state.modal.errorModalTitle;
};
var modalReducer = modalSlice.reducer;
function ownKeys$q(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$q(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$q(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$q(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var getCachedCustomRnaPresets = function getCachedCustomRnaPresets2() {
  return localStorageWrapper.getItem(CUSTOM_PRESETS);
};
var getPresetIndexInList = function getPresetIndexInList2(name) {
  var _presets$findIndex;
  var presets = getCachedCustomRnaPresets();
  return (_presets$findIndex = presets === null || presets === void 0 ? void 0 : presets.findIndex(function(cachedPreset) {
    return cachedPreset.name === name;
  })) !== null && _presets$findIndex !== void 0 ? _presets$findIndex : -1;
};
var setCachedCustomRnaPreset = function setCachedCustomRnaPreset2(preset) {
  var _getCachedCustomRnaPr;
  var presetToSet = _objectSpread$q({}, preset);
  var cachedPresets = (_getCachedCustomRnaPr = getCachedCustomRnaPresets()) !== null && _getCachedCustomRnaPr !== void 0 ? _getCachedCustomRnaPr : [];
  var presetIndexInCachedList = getPresetIndexInList(presetToSet.nameInList);
  presetToSet.nameInList = presetToSet.name;
  if (presetIndexInCachedList > -1) {
    cachedPresets.splice(presetIndexInCachedList, 1, presetToSet);
    localStorageWrapper.setItem(CUSTOM_PRESETS, cachedPresets);
  } else {
    localStorageWrapper.setItem(CUSTOM_PRESETS, [].concat(_toConsumableArray(cachedPresets), [presetToSet]));
  }
};
var deleteCachedCustomRnaPreset = function deleteCachedCustomRnaPreset2(presetName) {
  if (!presetName) return;
  var cachedPresets = getCachedCustomRnaPresets();
  var presetIndexInCachedList = getPresetIndexInList(presetName);
  if (cachedPresets) {
    cachedPresets.splice(presetIndexInCachedList, 1);
    if (cachedPresets.length) localStorageWrapper.setItem(CUSTOM_PRESETS, cachedPresets);
    else localStorageWrapper.removeItem(CUSTOM_PRESETS);
  }
};
var toggleCachedCustomRnaPresetFavorites = function toggleCachedCustomRnaPresetFavorites2(presetName) {
  if (!presetName) return;
  var cachedPresets = getCachedCustomRnaPresets();
  var presetIndexInCachedList = getPresetIndexInList(presetName);
  if (cachedPresets && presetIndexInCachedList > -1) {
    cachedPresets[presetIndexInCachedList].favorite = !cachedPresets[presetIndexInCachedList].favorite;
    localStorageWrapper.setItem(CUSTOM_PRESETS, cachedPresets);
  }
};
var transformRnaPresetToRnaLabeledPreset = function transformRnaPresetToRnaLabeledPreset2(rnaPreset) {
  var fieldsToLabel = ["sugar", "base", "phosphate"];
  var rnaLabeledPreset = omit(rnaPreset, fieldsToLabel);
  rnaLabeledPreset.templates = [];
  for (var _i = 0, _fieldsToLabel = fieldsToLabel; _i < _fieldsToLabel.length; _i++) {
    var _monomerLibraryItem$p, _monomerLibraryItem$p2;
    var monomerName = _fieldsToLabel[_i];
    var monomerLibraryItem = rnaPreset[monomerName];
    var templateId = (_monomerLibraryItem$p = monomerLibraryItem === null || monomerLibraryItem === void 0 || (_monomerLibraryItem$p2 = monomerLibraryItem.props) === null || _monomerLibraryItem$p2 === void 0 ? void 0 : _monomerLibraryItem$p2.id) !== null && _monomerLibraryItem$p !== void 0 ? _monomerLibraryItem$p : monomerLibraryItem === null || monomerLibraryItem === void 0 ? void 0 : monomerLibraryItem.id;
    if (!templateId) continue;
    rnaLabeledPreset.templates.push({
      $ref: monomerLibraryItem.isAmbiguous ? setAmbiguousMonomerTemplatePrefix(templateId) : setMonomerTemplatePrefix(templateId)
    });
  }
  rnaLabeledPreset.connections = buildRnaPresetConnections(rnaPreset, getRnaPresetPhosphatePosition(rnaPreset));
  return rnaLabeledPreset;
};
var hasCap = function hasCap2(presetPart, cap) {
  var _presetPart$props;
  return Boolean((presetPart === null || presetPart === void 0 || (_presetPart$props = presetPart.props) === null || _presetPart$props === void 0 ? void 0 : _presetPart$props.MonomerCaps) && cap in presetPart.props.MonomerCaps);
};
var getPhosphatePositionAvailability = function getPhosphatePositionAvailability2(newPreset) {
  var is3PrimeAvailable = (!(newPreset !== null && newPreset !== void 0 && newPreset.sugar) || hasCap(newPreset.sugar, "R2")) && (!(newPreset !== null && newPreset !== void 0 && newPreset.phosphate) || hasCap(newPreset.phosphate, "R1"));
  var is5PrimeAvailable = (!(newPreset !== null && newPreset !== void 0 && newPreset.sugar) || hasCap(newPreset.sugar, "R1")) && (!(newPreset !== null && newPreset !== void 0 && newPreset.phosphate) || hasCap(newPreset.phosphate, "R2"));
  return {
    is3PrimeAvailable,
    is5PrimeAvailable
  };
};
var getValidations = function getValidations2(newPreset, isEditMode, selectedPhosphatePosition) {
  var _newPreset$sugar;
  var sugarValidations = [];
  var phosphateValidations = [];
  var baseValidations = [];
  if (!isEditMode || !(newPreset !== null && newPreset !== void 0 && newPreset.sugar) && !(newPreset !== null && newPreset !== void 0 && newPreset.phosphate) && !(newPreset !== null && newPreset !== void 0 && newPreset.base)) {
    return {
      sugarValidations,
      phosphateValidations,
      baseValidations
    };
  }
  var _getPhosphatePosition = getPhosphatePositionAvailability(newPreset), is3PrimeAvailable = _getPhosphatePosition.is3PrimeAvailable, is5PrimeAvailable = _getPhosphatePosition.is5PrimeAvailable;
  if (selectedPhosphatePosition === "right") {
    sugarValidations.push("R2");
    phosphateValidations.push("R1");
  } else if (selectedPhosphatePosition === "left") {
    sugarValidations.push("R1");
    phosphateValidations.push("R2");
  } else {
    if (!is5PrimeAvailable) {
      phosphateValidations.push("R1");
      sugarValidations.push("R2");
    }
    if (!is3PrimeAvailable) {
      phosphateValidations.push("R2");
      sugarValidations.push("R1");
    }
  }
  if (newPreset !== null && newPreset !== void 0 && newPreset.base) {
    sugarValidations.push("R3");
  }
  baseValidations.push("R1");
  if (newPreset !== null && newPreset !== void 0 && (_newPreset$sugar = newPreset.sugar) !== null && _newPreset$sugar !== void 0 && (_newPreset$sugar = _newPreset$sugar.props) !== null && _newPreset$sugar !== void 0 && _newPreset$sugar.MonomerCaps && !hasCap(newPreset.sugar, "R3")) {
    baseValidations.push("DISABLED");
  }
  return {
    sugarValidations,
    phosphateValidations,
    baseValidations
  };
};
function ownKeys$p(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$p(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$p(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$p(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var RnaBuilderPresetsItem;
(function(RnaBuilderPresetsItem2) {
  RnaBuilderPresetsItem2["Presets"] = "Presets";
})(RnaBuilderPresetsItem || (RnaBuilderPresetsItem = {}));
var readPersistedPresetPhosphateFilter = function readPersistedPresetPhosphateFilter2() {
  var stored = localStorageWrapper.getItem(PRESET_PHOSPHATE_FILTER_STORAGE_KEY);
  if (stored && _typeof(stored) === "object" && typeof stored.fivePrime === "boolean" && typeof stored.threePrime === "boolean" && typeof stored.noPhosphate === "boolean") {
    return stored;
  }
  return {
    fivePrime: false,
    threePrime: false,
    noPhosphate: false
  };
};
var initialState = {
  activePreset: null,
  sequenceSelection: void 0,
  sequenceSelectionName: void 0,
  isSequenceFirstsOnlyNucleoelementsSelected: void 0,
  activePresetMonomerGroup: null,
  groupItemValidations: _defineProperty$1(_defineProperty$1(_defineProperty$1({}, MonomerGroups.BASES, []), MonomerGroups.SUGARS, []), MonomerGroups.PHOSPHATES, []),
  presetsDefault: [],
  presetsCustom: [],
  activeRnaBuilderItem: null,
  activeMonomerKey: null,
  isEditMode: false,
  uniqueNameError: "",
  invalidPresetError: "",
  activePresetForContextMenu: null,
  presetPhosphateFilter: readPersistedPresetPhosphateFilter()
};
var monomerGroupToPresetGroup = _defineProperty$1(_defineProperty$1(_defineProperty$1({}, MonomerGroups.BASES, "base"), MonomerGroups.SUGARS, "sugar"), MonomerGroups.PHOSPHATES, "phosphate");
var rnaBuilderSlice = createSlice({
  name: "rna-builder",
  initialState,
  reducers: {
    createNewPreset: function createNewPreset(state) {
      state.activePreset = {
        base: void 0,
        sugar: void 0,
        phosphate: void 0,
        name: "",
        nameInList: ""
      };
    },
    setActivePreset: function setActivePreset(state, action) {
      state.activePreset = _objectSpread$p(_objectSpread$p({}, action.payload), {}, {
        nameInList: action.payload.name
      });
    },
    setSequenceSelection: function setSequenceSelection(state, action) {
      state.sequenceSelection = _toConsumableArray(action.payload);
    },
    setSequenceSelectionName: function setSequenceSelectionName(state, action) {
      state.sequenceSelectionName = action.payload;
    },
    setIsSequenceFirstsOnlyNucleoelementsSelected: function setIsSequenceFirstsOnlyNucleoelementsSelected(state, action) {
      state.isSequenceFirstsOnlyNucleoelementsSelected = action.payload;
    },
    setActivePresetForContextMenu: function setActivePresetForContextMenu(state, action) {
      state.activePresetForContextMenu = action.payload;
    },
    setPresetPhosphateFilter: function setPresetPhosphateFilter(state, action) {
      state.presetPhosphateFilter = action.payload;
      localStorageWrapper.setItem(PRESET_PHOSPHATE_FILTER_STORAGE_KEY, action.payload);
    },
    setActivePresetName: function setActivePresetName(state, action) {
      state.activePreset.name = action.payload;
    },
    setActiveRnaBuilderItem: function setActiveRnaBuilderItem(state, action) {
      state.activeRnaBuilderItem = action.payload;
    },
    recalculateRnaBuilderValidations: function recalculateRnaBuilderValidations(state, action) {
      var _action$payload$selec;
      var _getValidations = getValidations(action.payload.rnaPreset, action.payload.isEditMode, (_action$payload$selec = action.payload.selectedPhosphatePosition) !== null && _action$payload$selec !== void 0 ? _action$payload$selec : getRnaPresetPhosphatePosition(action.payload.rnaPreset)), sugarValidations = _getValidations.sugarValidations, phosphateValidations = _getValidations.phosphateValidations, baseValidations = _getValidations.baseValidations;
      state.groupItemValidations[MonomerGroups.SUGARS] = sugarValidations;
      state.groupItemValidations[MonomerGroups.BASES] = baseValidations;
      state.groupItemValidations[MonomerGroups.PHOSPHATES] = phosphateValidations;
    },
    setActivePresetMonomerGroup: function setActivePresetMonomerGroup(state, action) {
      state.activePresetMonomerGroup = action.payload;
    },
    savePreset: function savePreset(state, action) {
      var preset = action.payload;
      var newPreset = _objectSpread$p({}, preset);
      setCachedCustomRnaPreset(transformRnaPresetToRnaLabeledPreset(newPreset));
      if (newPreset.nameInList) {
        var presetIndexInList = state.presetsCustom.findIndex(function(presetInList) {
          return presetInList.name === newPreset.nameInList;
        });
        newPreset.nameInList = newPreset.name;
        presetIndexInList === -1 ? state.presetsCustom.push(newPreset) : state.presetsCustom.splice(presetIndexInList, 1, newPreset);
      } else {
        state.presetsCustom.push(newPreset);
      }
      if (!state.activePreset) return;
      state.activePreset.nameInList = newPreset.name;
    },
    deletePreset: function deletePreset(state, action) {
      var preset = action.payload;
      deleteCachedCustomRnaPreset(preset.name);
      var presetIndexInList = state.presetsCustom.findIndex(function(presetInList) {
        return presetInList.name === preset.name;
      });
      state.presetsCustom.splice(presetIndexInList, 1);
      if (preset.nameInList) {
        state.activePreset = null;
      }
    },
    setIsEditMode: function setIsEditMode(state, action) {
      state.isEditMode = action.payload;
    },
    setUniqueNameError: function setUniqueNameError(state, action) {
      state.uniqueNameError = action.payload;
    },
    setInvalidPresetError: function setInvalidPresetError(state, action) {
      state.invalidPresetError = action.payload;
    },
    setDefaultPresets: function setDefaultPresets(state, action) {
      var defaultNucleotide = action.payload[0];
      if (!defaultNucleotide) {
        return;
      }
      var presetExists = state.presetsDefault.find(function(item) {
        return item.name === defaultNucleotide.name;
      });
      if (presetExists) {
        return;
      }
      state.presetsDefault = action.payload;
    },
    setCustomPresets: function setCustomPresets(state, action) {
      state.presetsCustom = action.payload;
    },
    setFavoritePresetsFromLocalStorage: function setFavoritePresetsFromLocalStorage(state) {
      var favoritesInLocalStorage = localStorageWrapper.getItem(FAVORITE_ITEMS_UNIQUE_KEYS);
      if (!favoritesInLocalStorage || !Array.isArray(favoritesInLocalStorage)) {
        return;
      }
      state.presetsDefault = state.presetsDefault.map(function(preset) {
        var uniqueKey = "".concat(preset.name, "_").concat(MONOMER_CONST.RNA);
        var favoriteItem = favoritesInLocalStorage.find(function(key) {
          return key === uniqueKey;
        });
        if (favoriteItem) {
          return _objectSpread$p(_objectSpread$p({}, preset), {}, {
            favorite: true
          });
        }
        return preset;
      });
    },
    clearFavorites: function clearFavorites2(state) {
      state.presetsDefault = [];
    },
    setActiveMonomerKey: function setActiveMonomerKey(state, action) {
      state.activeMonomerKey = action.payload;
    },
    togglePresetFavorites: function togglePresetFavorites(state, action) {
      var _localStorageWrapper$;
      var presetIndex = state.presetsDefault.findIndex(function(presetInList) {
        return presetInList.name === action.payload.name;
      });
      var presetCustomIndex = state.presetsCustom.findIndex(function(presetInList) {
        return presetInList.name === action.payload.name;
      });
      if (presetIndex >= 0) {
        var favorite = state.presetsDefault[presetIndex].favorite;
        state.presetsDefault[presetIndex].favorite = !favorite;
      } else if (presetCustomIndex >= 0) {
        toggleCachedCustomRnaPresetFavorites(state.presetsCustom[presetCustomIndex].name);
        var _favorite = state.presetsCustom[presetCustomIndex].favorite;
        state.presetsCustom[presetCustomIndex].favorite = !_favorite;
        return;
      }
      var uniquePresetKey = "".concat(action.payload.name, "_").concat(MONOMER_CONST.RNA);
      var favoriteItemsUniqueKeys = (_localStorageWrapper$ = localStorageWrapper.getItem(FAVORITE_ITEMS_UNIQUE_KEYS)) !== null && _localStorageWrapper$ !== void 0 ? _localStorageWrapper$ : [];
      var isKeyAlreadyExisted = favoriteItemsUniqueKeys.some(function(targetKey) {
        return targetKey === uniquePresetKey;
      });
      if (isKeyAlreadyExisted) {
        localStorageWrapper.setItem(FAVORITE_ITEMS_UNIQUE_KEYS, favoriteItemsUniqueKeys.filter(function(targetKey) {
          return targetKey !== uniquePresetKey;
        }));
      } else {
        favoriteItemsUniqueKeys.push(uniquePresetKey);
        localStorageWrapper.setItem(FAVORITE_ITEMS_UNIQUE_KEYS, favoriteItemsUniqueKeys);
      }
    }
  }
});
var selectRnaBuilderSlice = function selectRnaBuilderSlice2(state) {
  return state.rnaBuilder;
};
var selectActiveRnaBuilderItem = function selectActiveRnaBuilderItem2(state) {
  return state.rnaBuilder.activeRnaBuilderItem;
};
var selectGroupItemValidations = function selectGroupItemValidations2(state) {
  return state.rnaBuilder.groupItemValidations;
};
var selectActivePreset = function selectActivePreset2(state) {
  return state.rnaBuilder.activePreset;
};
var selectSequenceSelection = function selectSequenceSelection2(state) {
  return state.rnaBuilder.sequenceSelection;
};
var selectSequenceSelectionName = function selectSequenceSelectionName2(state) {
  return state.rnaBuilder.sequenceSelectionName;
};
var selectIsSequenceFirstsOnlyNucleotidesSelected = function selectIsSequenceFirstsOnlyNucleotidesSelected2(state) {
  return state.rnaBuilder.isSequenceFirstsOnlyNucleoelementsSelected;
};
var selectCurrentMonomerGroup = function selectCurrentMonomerGroup2(preset, groupName) {
  if (!monomerGroupToPresetGroup[groupName] || !preset) return;
  return preset[monomerGroupToPresetGroup[groupName]];
};
var selectActivePresetMonomerGroup = function selectActivePresetMonomerGroup2(state) {
  return state.rnaBuilder.activePresetMonomerGroup;
};
var selectIsPresetReadyToSave = function selectIsPresetReadyToSave2(preset) {
  return Boolean(preset.name && preset.sugar && (preset.base || preset.phosphate));
};
var selectIsEditMode = function selectIsEditMode2(state) {
  return state.rnaBuilder.isEditMode;
};
var selectPresetFullName = function selectPresetFullName2(preset) {
  var _ref3, _preset$sugar$label, _preset$sugar, _preset$sugar2, _ref22, _preset$base$label, _preset$base, _preset$base2, _ref32, _preset$phosphate$lab, _preset$phosphate, _preset$phosphate2;
  if (!preset) return "";
  var sugar = (_ref3 = (_preset$sugar$label = (_preset$sugar = preset.sugar) === null || _preset$sugar === void 0 ? void 0 : _preset$sugar.label) !== null && _preset$sugar$label !== void 0 ? _preset$sugar$label : (_preset$sugar2 = preset.sugar) === null || _preset$sugar2 === void 0 ? void 0 : _preset$sugar2.props.MonomerName) !== null && _ref3 !== void 0 ? _ref3 : "";
  var base = (_ref22 = (_preset$base$label = (_preset$base = preset.base) === null || _preset$base === void 0 ? void 0 : _preset$base.label) !== null && _preset$base$label !== void 0 ? _preset$base$label : (_preset$base2 = preset.base) === null || _preset$base2 === void 0 ? void 0 : _preset$base2.props.MonomerName) !== null && _ref22 !== void 0 ? _ref22 : "";
  var phosphate = (_ref32 = (_preset$phosphate$lab = (_preset$phosphate = preset.phosphate) === null || _preset$phosphate === void 0 ? void 0 : _preset$phosphate.label) !== null && _preset$phosphate$lab !== void 0 ? _preset$phosphate$lab : (_preset$phosphate2 = preset.phosphate) === null || _preset$phosphate2 === void 0 ? void 0 : _preset$phosphate2.props.MonomerName) !== null && _ref32 !== void 0 ? _ref32 : "";
  var phosphatePosition = getRnaPresetPhosphatePosition(preset);
  var fullName = sugar;
  if (sugar && phosphate) {
    fullName += "(".concat(base, ")");
  } else if ((sugar || phosphate) && base) {
    fullName += "(".concat(base, ")");
  } else {
    fullName += base;
  }
  if (phosphate) {
    fullName = phosphatePosition === "left" ? "".concat(phosphate).concat(fullName) : "".concat(fullName).concat(phosphate);
  }
  return fullName;
};
var selectUniqueNameError = function selectUniqueNameError2(state) {
  return state.rnaBuilder.uniqueNameError;
};
var selectInvalidPresetError = function selectInvalidPresetError2(state) {
  return state.rnaBuilder.invalidPresetError;
};
var selectIsActivePresetNewAndEmpty = function selectIsActivePresetNewAndEmpty2(state) {
  var activePreset = state.rnaBuilder.activePreset;
  return activePreset && !activePreset.nameInList && !activePreset.name && !activePreset.sugar && !activePreset.base && !activePreset.phosphate;
};
var selectActivePresetForContextMenu = function selectActivePresetForContextMenu2(state) {
  return state.rnaBuilder.activePresetForContextMenu;
};
var selectPresetPhosphateFilter = function selectPresetPhosphateFilter2(state) {
  return state.rnaBuilder.presetPhosphateFilter;
};
var selectPresetsInFavorites = function selectPresetsInFavorites2(items) {
  return items.filter(function(item) {
    return item.favorite;
  });
};
var selectActiveMonomerKey = function selectActiveMonomerKey2(state) {
  return state.rnaBuilder.activeMonomerKey;
};
var selectAllPresets = createSelector(selectRnaBuilderSlice, function(rnaBuilderSlice2) {
  var _rnaBuilderSlice$pres = rnaBuilderSlice2.presetsDefault, presetsDefault = _rnaBuilderSlice$pres === void 0 ? [] : _rnaBuilderSlice$pres, _rnaBuilderSlice$pres2 = rnaBuilderSlice2.presetsCustom, presetsCustom = _rnaBuilderSlice$pres2 === void 0 ? [] : _rnaBuilderSlice$pres2;
  return [].concat(_toConsumableArray(presetsDefault), _toConsumableArray(presetsCustom));
});
var selectFilteredPresets = createSelector(selectAllPresets, selectSearchFilter, selectAxoLabsAliasesByPresetName, selectPresetPhosphateFilter, function(presetsAll, searchFilter, axoLabsAliasesByPresetName, phosphateFilter) {
  var searchText = searchFilter.toLowerCase();
  return presetsAll.filter(function(item) {
    var _item$name, _item$sugar, _item$phosphate, _item$base, _item$idtAliases, _ref4, _item$aliasAxoLabs$to, _item$aliasAxoLabs, _item$idtAliases2, _item$name2, _searchText$match, _transformedIdtText3;
    var name = (_item$name = item.name) === null || _item$name === void 0 ? void 0 : _item$name.toLowerCase();
    var sugarName = (_item$sugar = item.sugar) === null || _item$sugar === void 0 || (_item$sugar = _item$sugar.label) === null || _item$sugar === void 0 ? void 0 : _item$sugar.toLowerCase();
    var phosphateName = (_item$phosphate = item.phosphate) === null || _item$phosphate === void 0 || (_item$phosphate = _item$phosphate.label) === null || _item$phosphate === void 0 ? void 0 : _item$phosphate.toLowerCase();
    var baseName = (_item$base = item.base) === null || _item$base === void 0 || (_item$base = _item$base.label) === null || _item$base === void 0 ? void 0 : _item$base.toLowerCase();
    var idtName = (_item$idtAliases = item.idtAliases) === null || _item$idtAliases === void 0 || (_item$idtAliases = _item$idtAliases.base) === null || _item$idtAliases === void 0 ? void 0 : _item$idtAliases.toLowerCase();
    var axoLabsAlias = (_ref4 = (_item$aliasAxoLabs$to = (_item$aliasAxoLabs = item.aliasAxoLabs) === null || _item$aliasAxoLabs === void 0 ? void 0 : _item$aliasAxoLabs.toLowerCase()) !== null && _item$aliasAxoLabs$to !== void 0 ? _item$aliasAxoLabs$to : name ? axoLabsAliasesByPresetName.get(name) : void 0) !== null && _ref4 !== void 0 ? _ref4 : "";
    var modifications = (_item$idtAliases2 = item.idtAliases) === null || _item$idtAliases2 === void 0 ? void 0 : _item$idtAliases2.modifications;
    var transformedIdtText = idtName;
    if (idtName && (_item$name2 = item.name) !== null && _item$name2 !== void 0 && _item$name2.includes("MOE")) {
      var _modifications$endpoi, _modifications$intern;
      var base = idtName;
      var endpoint5 = (_modifications$endpoi = modifications === null || modifications === void 0 ? void 0 : modifications.endpoint5) !== null && _modifications$endpoi !== void 0 ? _modifications$endpoi : "5".concat(base);
      var internal = (_modifications$intern = modifications === null || modifications === void 0 ? void 0 : modifications.internal) !== null && _modifications$intern !== void 0 ? _modifications$intern : "i".concat(base);
      transformedIdtText = "".concat(endpoint5, ", ").concat(internal);
    }
    var slashCount = ((_searchText$match = searchText.match(/\//g)) !== null && _searchText$match !== void 0 ? _searchText$match : []).length;
    var parts = searchText.split("/");
    if (slashCount >= 2 && parts[2] !== void 0 && parts[2] !== "") {
      return false;
    }
    if (searchText.startsWith("/") && searchText.length > 1) {
      var _transformedIdtText;
      var aliasRest = searchText.slice(1);
      return ((_transformedIdtText = transformedIdtText) === null || _transformedIdtText === void 0 ? void 0 : _transformedIdtText.toLowerCase().startsWith(aliasRest)) || (idtName === null || idtName === void 0 ? void 0 : idtName.startsWith(aliasRest)) || modifications && Object.values(modifications).some(function(mod) {
        return mod === null || mod === void 0 ? void 0 : mod.toLowerCase().startsWith(aliasRest);
      });
    }
    if (searchText.endsWith("/") && searchText.length > 1) {
      var _transformedIdtText2;
      var _aliasRest = searchText.slice(0, -1);
      var aliasLastSymbol = searchText[searchText.length - 2];
      return ((_transformedIdtText2 = transformedIdtText) === null || _transformedIdtText2 === void 0 ? void 0 : _transformedIdtText2.toLowerCase().endsWith(_aliasRest)) && transformedIdtText[transformedIdtText.length - 1] === aliasLastSymbol || (idtName === null || idtName === void 0 ? void 0 : idtName.endsWith(_aliasRest)) && idtName[idtName.length - 1] === aliasLastSymbol || modifications && Object.values(modifications).some(function(mod) {
        return (mod === null || mod === void 0 ? void 0 : mod.toLowerCase().endsWith(_aliasRest)) && mod[mod.length - 1] === aliasLastSymbol;
      });
    }
    if (searchText === "/") {
      return !!item.idtAliases;
    }
    return (name === null || name === void 0 ? void 0 : name.includes(searchText)) || (sugarName === null || sugarName === void 0 ? void 0 : sugarName.includes(searchText)) || (phosphateName === null || phosphateName === void 0 ? void 0 : phosphateName.includes(searchText)) || (baseName === null || baseName === void 0 ? void 0 : baseName.includes(searchText)) || ((_transformedIdtText3 = transformedIdtText) === null || _transformedIdtText3 === void 0 ? void 0 : _transformedIdtText3.toLowerCase().includes(searchText)) || axoLabsAlias.includes(searchText);
  }).filter(function(item) {
    if (!phosphateFilter) {
      return true;
    }
    var fivePrime = phosphateFilter.fivePrime, threePrime = phosphateFilter.threePrime, noPhosphate = phosphateFilter.noPhosphate;
    var allOn = fivePrime && threePrime && noPhosphate;
    var allOff = !fivePrime && !threePrime && !noPhosphate;
    if (allOn || allOff) {
      return true;
    }
    if (!item.phosphate) {
      return noPhosphate;
    }
    var position = getRnaPresetPhosphatePosition(item);
    return position === "left" ? fivePrime : threePrime;
  });
});
var _rnaBuilderSlice$acti = rnaBuilderSlice.actions, setActivePreset2 = _rnaBuilderSlice$acti.setActivePreset, setSequenceSelection2 = _rnaBuilderSlice$acti.setSequenceSelection, setSequenceSelectionName2 = _rnaBuilderSlice$acti.setSequenceSelectionName, setIsSequenceFirstsOnlyNucleoelementsSelected2 = _rnaBuilderSlice$acti.setIsSequenceFirstsOnlyNucleoelementsSelected;
_rnaBuilderSlice$acti.setActivePresetName;
var setActiveRnaBuilderItem2 = _rnaBuilderSlice$acti.setActiveRnaBuilderItem, setActiveMonomerKey2 = _rnaBuilderSlice$acti.setActiveMonomerKey, recalculateRnaBuilderValidations2 = _rnaBuilderSlice$acti.recalculateRnaBuilderValidations, setActivePresetMonomerGroup2 = _rnaBuilderSlice$acti.setActivePresetMonomerGroup, savePreset2 = _rnaBuilderSlice$acti.savePreset, deletePreset2 = _rnaBuilderSlice$acti.deletePreset, createNewPreset2 = _rnaBuilderSlice$acti.createNewPreset, setIsEditMode2 = _rnaBuilderSlice$acti.setIsEditMode, setUniqueNameError2 = _rnaBuilderSlice$acti.setUniqueNameError, setInvalidPresetError2 = _rnaBuilderSlice$acti.setInvalidPresetError, setDefaultPresets2 = _rnaBuilderSlice$acti.setDefaultPresets, setCustomPresets2 = _rnaBuilderSlice$acti.setCustomPresets, setActivePresetForContextMenu2 = _rnaBuilderSlice$acti.setActivePresetForContextMenu, setPresetPhosphateFilter2 = _rnaBuilderSlice$acti.setPresetPhosphateFilter, togglePresetFavorites2 = _rnaBuilderSlice$acti.togglePresetFavorites, setFavoritePresetsFromLocalStorage2 = _rnaBuilderSlice$acti.setFavoritePresetsFromLocalStorage, clearFavorites3 = _rnaBuilderSlice$acti.clearFavorites;
var rnaBuilderReducer = rnaBuilderSlice.reducer;
function configureAppStore() {
  var preloadedState = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : {};
  var store2 = configureStore({
    reducer: {
      editor: editorReducer,
      modal: modalReducer,
      library: libraryReducer,
      rnaBuilder: rnaBuilderReducer
    },
    middleware: function middleware(getDefaultMiddleware) {
      return getDefaultMiddleware({
        serializableCheck: false
      });
    },
    preloadedState
  });
  return store2;
}
var store = configureAppStore();
var monomerColors = {
  colorA: {
    regular: "#5ADC11",
    hover: "#4FC218"
  },
  colorCM: {
    regular: "#59D0FF",
    hover: "#3CB9EB"
  },
  colorDQ: {
    regular: "#AD4551",
    hover: "#AB0014"
  },
  colorEN: {
    regular: "#93F5F5",
    hover: "#00F0F0"
  },
  colorFY: {
    regular: "#5656BF",
    hover: "#2626BF"
  },
  colorGX: {
    regular: "#FFE97B",
    hover: "#F8DC50"
  },
  colorH: {
    regular: "#BFC9FF",
    hover: "#99AAFF"
  },
  colorILV: {
    regular: "#50E576",
    hover: "#00D936"
  },
  colorKR: {
    regular: "#365CFF",
    hover: "#002CEB"
  },
  colorP: {
    regular: "#F2C5B6",
    hover: "#FFA98C"
  },
  colorST: {
    regular: "#FF8D8D",
    hover: "#ED6868"
  },
  colorW: {
    regular: "#99458B",
    hover: "#7F006B"
  },
  colorU: {
    regular: "#FF973C",
    hover: "#2EE55D"
  },
  colorX: {
    regular: "#CAD3DD",
    hover: "#B8BBCC"
  },
  chem: {
    regular: "#333333",
    hover: "#555555"
  },
  "default": {
    regular: "#CCCBD6",
    hover: "#B8BBCC"
  }
};
var peptideColorScheme = {
  D: {
    regular: "#FF8C69",
    hover: "#0097A8"
  },
  E: {
    regular: "#DC143C",
    hover: "#0097A8"
  },
  K: {
    regular: "#B0E0E6",
    hover: "#0097A8"
  },
  H: {
    regular: "#007FFF",
    hover: "#0097A8"
  },
  O: {
    regular: "#2A52BE",
    hover: "#0097A8"
  },
  R: {
    regular: "#0A12FF",
    hover: "#0097A8"
  },
  Q: {
    regular: "#EDB4ED",
    hover: "#0097A8"
  },
  Y: {
    regular: "#D65CBC",
    hover: "#0097A8"
  },
  U: {
    regular: "#CA7DE3",
    hover: "#0097A8"
  },
  S: {
    regular: "#9966CC",
    hover: "#0097A8"
  },
  C: {
    regular: "#BF00FF",
    hover: "#0097A8"
  },
  N: {
    regular: "#800080",
    hover: "#0097A8"
  },
  T: {
    regular: "#FF00FF",
    hover: "#0097A8"
  },
  L: {
    regular: "#7FFF00",
    hover: "#0097A8"
  },
  I: {
    regular: "#4CBB17",
    hover: "#0097A8"
  },
  F: {
    regular: "#008A00",
    hover: "#0097A8"
  },
  A: {
    regular: "#008080",
    hover: "#0097A8"
  },
  W: {
    regular: "#50E576",
    hover: "#0097A8"
  },
  P: {
    regular: "#D2D900",
    hover: "#0097A8"
  },
  G: {
    regular: "#BDB76B",
    hover: "#0097A8"
  },
  M: {
    regular: "#FFF600",
    hover: "#0097A8"
  },
  V: {
    regular: "#FFD700",
    hover: "#0097A8"
  }
};
var defaultTheme = {
  color: {
    background: {
      canvas: "#F5F5F5",
      primary: "#FFFFFF",
      secondary: "#F8FEFF",
      overlay: "rgba(94,94,94,.8)"
    },
    border: {
      primary: "#CAD3DD",
      secondary: "#7C7C7F"
    },
    text: {
      primary: "#333333",
      secondary: "#167782",
      light: "#585858",
      dark: "#000000",
      error: "#FF4A4A",
      lightgrey: "#7C7C7F"
    },
    tab: {
      regular: "#FFFFFF",
      active: "#E1E5EA",
      hover: "#00838F",
      content: "#EFF2F5"
    },
    scroll: {
      regular: "#717171",
      inactive: "#DDDDDD"
    },
    button: {
      primary: {
        active: "#167782",
        hover: "#00838F",
        clicked: "#4FB3BF",
        disabled: "rgba(113, 113, 113, 0.4)"
      },
      secondary: {
        active: "#585858",
        hover: "#333333",
        clicked: "#AEAEAE",
        disabled: "rgba(113, 113, 113, 0.4)"
      },
      group: {
        active: "#167782",
        hover: "#2E858F"
      },
      transparent: {
        active: "transparent"
      },
      text: {
        primary: "#FFFFFF",
        secondary: "#005662",
        disabled: "#7A7A7A"
      }
    },
    dropdown: {
      primary: "#333333",
      secondary: "#FFFFFF",
      hover: "#DDDDDD",
      disabled: "#7A7A7A"
    },
    tooltip: {
      background: "#FFFFFF",
      text: "#333333"
    },
    link: {
      active: "#00838F",
      hover: "#005662"
    },
    divider: "#AEAEAE",
    spinner: "#005662",
    error: "#FF4A4A",
    input: {
      text: {
        "default": "#585858",
        active: "#333333",
        disabled: "#585858",
        error: "#FF4A4A"
      },
      background: {
        primary: "#FFFFFF",
        "default": "#EFF2F5",
        hover: "#DDDDDD",
        disabled: "#eff2f5"
      },
      border: {
        regular: "#cad3dd",
        active: "#FFFFFF",
        hover: "#43b5c0",
        focus: "#EFF2F5",
        error: "#FF4A4A"
      }
    },
    icon: {
      grey: "#B4B9D6",
      hover: "#005662",
      active: "#525252",
      activeMenu: "#005662",
      clicked: "#FFFFFF",
      disabled: "rgba(82, 82, 82, 0.4)"
    },
    monomer: {
      "default": "#C8C8C8"
    },
    editMode: {
      sequenceInRNABuilder: "#99d7dc"
    }
  },
  font: {
    size: {
      small: "10px",
      regular: "12px",
      medium: "14px",
      xsmall: "6px"
    },
    family: {
      montserrat: "Montserrat, sans-serif",
      inter: "Inter, FreeSans, Arimo, 'Droid Sans', Helvetica, 'Helvetica Neue',\nArial, sans-serif",
      roboto: "Roboto, FreeSans, Arimo, Droid Sans, Helvetica, Helvetica Neue, Arial, sans-serif"
    },
    weight: {
      light: 300,
      regular: 400,
      bold: 600
    }
  },
  monomer: {
    color: {
      A: monomerColors.colorA,
      C: monomerColors.colorCM,
      M: monomerColors.colorCM,
      D: monomerColors.colorDQ,
      Q: monomerColors.colorDQ,
      E: monomerColors.colorEN,
      N: monomerColors.colorEN,
      F: monomerColors.colorFY,
      Y: monomerColors.colorFY,
      G: monomerColors.colorGX,
      X: monomerColors.colorX,
      Other: monomerColors.colorX,
      H: monomerColors.colorH,
      I: monomerColors.colorILV,
      L: monomerColors.colorILV,
      V: monomerColors.colorILV,
      K: monomerColors.colorKR,
      R: monomerColors.colorKR,
      P: monomerColors.colorP,
      S: monomerColors.colorST,
      T: monomerColors.colorST,
      W: monomerColors.colorW,
      U: monomerColors.colorU,
      CHEM: monomerColors.chem,
      "default": monomerColors["default"]
    }
  },
  peptide: {
    color: {
      D: peptideColorScheme.D,
      E: peptideColorScheme.E,
      K: peptideColorScheme.K,
      H: peptideColorScheme.H,
      O: peptideColorScheme.O,
      R: peptideColorScheme.R,
      Q: peptideColorScheme.Q,
      Y: peptideColorScheme.Y,
      U: peptideColorScheme.U,
      S: peptideColorScheme.S,
      C: peptideColorScheme.C,
      N: peptideColorScheme.N,
      T: peptideColorScheme.T,
      L: peptideColorScheme.L,
      I: peptideColorScheme.I,
      F: peptideColorScheme.F,
      A: peptideColorScheme.A,
      W: peptideColorScheme.W,
      P: peptideColorScheme.P,
      G: peptideColorScheme.G,
      M: peptideColorScheme.M,
      V: peptideColorScheme.V,
      Other: monomerColors.colorX
    }
  },
  border: {
    regular: "1px solid #CAD3DD",
    small: "1px solid #E1E5EA",
    radius: {
      regular: "4px"
    }
  },
  shadow: {
    regular: "0px 1px 1px rgba(197, 203, 207, 0.7)",
    mainLayoutBlocks: "0px 2px 5px rgba(103, 104, 132, 0.15)"
  },
  outline: {
    small: "1px solid #B4B9D6",
    medium: "2px solid #B4B9D6",
    color: "#B4B9D6",
    selected: {
      color: "#167782",
      small: "1px solid #167782",
      medium: "2px solid #167782"
    },
    grey: {
      small: "1px solid #585858"
    }
  },
  transition: {
    regular: "all .3s"
  },
  zIndex: {
    base: 0,
    toolbar: 10,
    sticky: 100,
    overlay: 200,
    modal: 1e3,
    critical: 9999
  }
};
var muiOverrides = {};
var getGlobalStyles = function getGlobalStyles2(theme) {
  return css({
    all: "unset",
    ".Ketcher-polymer-editor-root": {
      all: "unset",
      fontSize: theme.ketcher.font.size.medium,
      fontFamily: theme.ketcher.font.family.inter,
      fontWeight: theme.ketcher.font.weight.regular,
      backgroundColor: theme.ketcher.color.background.primary,
      color: theme.ketcher.color.text.primary,
      boxSizing: "border-box"
    },
    ":where(.Ketcher-polymer-editor-root) div": {
      boxSizing: "border-box"
    },
    ":where(.Ketcher-polymer-editor-root) input": {
      fontFamily: theme.ketcher.font.family.inter,
      fontWeight: theme.ketcher.font.weight.regular,
      fontSize: theme.ketcher.font.size.regular,
      boxSizing: "border-box"
    },
    ":where(.Ketcher-polymer-editor-root) h1": {
      fontSize: 96
    },
    ":where(.Ketcher-polymer-editor-root) h2": {
      fontSize: 60
    },
    ":where(.Ketcher-polymer-editor-root) h3": {
      fontSize: 48
    },
    ":where(.Ketcher-polymer-editor-root) h4": {
      fontSize: 34
    },
    ":where(.Ketcher-polymer-editor-root) h5": {
      fontSize: 24
    },
    ":where(.Ketcher-polymer-editor-root) h6": {
      fontSize: 20,
      fontWeight: theme.ketcher.font.weight.bold
    },
    ":where(.Ketcher-polymer-editor-root) p": {
      fontSize: theme.ketcher.font.size.regular
    },
    ":where(.Ketcher-polymer-editor-root) button": {
      textTransform: "uppercase",
      fontWeight: theme.ketcher.font.weight.bold
    }
  }, "" , "" );
};
var MONOMER_LIBRARY_WIDTH = "254px";
var MONOMER_HIDE_LIBRARY_BUTTON_WIDTH = "100px";
var MonomerLibraryContainer = createStyled("div", {
  target: "e1vkl5kv5"
} )("width:", MONOMER_LIBRARY_WIDTH, ";height:calc(100% - 16px);display:flex;flex-direction:column;background-color:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.color.background.primary;
}, ";box-shadow:", function(_ref22) {
  var theme = _ref22.theme;
  return theme.ketcher.shadow.mainLayoutBlocks;
}, ";border-radius:4px;z-index:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.zIndex.toolbar;
}, ";" + ("" ));
var MonomerLibraryHeader = createStyled("div", {
  target: "e1vkl5kv4"
} )({
  name: "n1y6qf",
  styles: "padding:10px 0 10px 8px;position:relative;display:flex;align-items:center;gap:8px"
} );
var MonomerLibraryInputContainer = createStyled("div", {
  target: "e1vkl5kv3"
} )("height:24px;display:flex;flex-grow:1;gap:4px;align-items:center;padding:4px;background-color:", function(_ref4) {
  var theme = _ref4.theme;
  return theme.ketcher.color.input.background["default"];
}, ";border-radius:4px;&:hover,&:has(input:focus){outline:", function(_ref5) {
  var theme = _ref5.theme;
  return theme.ketcher.outline.selected.small;
}, ";}" + ("" ));
var MonomerLibraryToggle$1 = createStyled("button", {
  target: "e1vkl5kv2"
} )("height:24px;display:flex;align-items:center;gap:2px;border:none;border-radius:4px 0 0 4px;cursor:pointer;background-color:#e2e5e9;text-transform:none;font-weight:", function(_ref6) {
  var theme = _ref6.theme;
  return theme.ketcher.font.weight.regular;
}, ";font-size:", function(_ref7) {
  var theme = _ref7.theme;
  return theme.ketcher.font.size.regular;
}, ";color:", function(_ref8) {
  var theme = _ref8.theme;
  return theme.ketcher.color.text.secondary;
}, ";" + ("" ));
var MonomerLibrarySearchIcon = createStyled(Icon, {
  target: "e1vkl5kv1"
} )("height:16px;width:16px;color:", function(_ref9) {
  var theme = _ref9.theme;
  return theme.ketcher.color.text.secondary;
}, ";" + ("" ));
var MonomerLibraryInput = createStyled(Input$2, {
  target: "e1vkl5kv0"
} )({
  name: "pmmg8c",
  styles: "flex-grow:1;padding:0;margin:0;background-color:transparent;border:none;outline:none;&:hover{outline:none;}&:focus{outline:none;}"
} );
var _excluded$4 = ["children"];
function ownKeys$o(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$o(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$o(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$o(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var Column = createStyled("div", {
  target: "e1pv9pa12"
} )(function(_ref3) {
  var fullWidth = _ref3.fullWidth, withPaddingRight = _ref3.withPaddingRight;
  return {
    width: fullWidth ? "100%" : "fit-content",
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    paddingRight: withPaddingRight ? "12px" : 0,
    overflow: fullWidth ? "hidden" : "initial"
  };
}, "" );
var RowMain = createStyled("div", {
  target: "e1pv9pa11"
} )(function(_ref22) {
  var theme = _ref22.theme;
  return {
    height: "100%",
    width: "100%",
    position: "relative",
    padding: "12px",
    paddingBottom: 0,
    backgroundColor: theme.ketcher.color.background.canvas,
    display: "flex",
    justifyContent: "space-between",
    containerType: "size",
    overflow: "clip"
  };
}, "" );
var Row$1 = createStyled("div", {
  target: "e1pv9pa10"
} )(function(_ref3) {
  var theme = _ref3.theme;
  return {
    height: "100%",
    width: "100%",
    position: "relative",
    paddingBottom: 0,
    backgroundColor: theme.ketcher.color.background.canvas,
    display: "flex",
    justifyContent: "space-between",
    columnGap: "3px"
  };
}, "" );
var BaseLeftRightStyle = createStyled("div", {
  target: "e1pv9pa9"
} )(function(_ref4) {
  var _ref4$hide = _ref4.hide, hide = _ref4$hide === void 0 ? false : _ref4$hide;
  return {
    height: "100%",
    width: "fit-content",
    display: hide ? "none" : "flex",
    flexDirection: "column"
  };
}, "" );
var Left = createStyled(BaseLeftRightStyle, {
  target: "e1pv9pa8"
} )("" );
var Right = createStyled(BaseLeftRightStyle, {
  target: "e1pv9pa7"
} )("" );
var StyledTopInnerDiv = createStyled("div", {
  target: "e1pv9pa6"
} )({
  name: "oixulj",
  styles: "display:flex;justify-content:space-between;width:100cqw"
} );
var StyledTop = createStyled("div", {
  target: "e1pv9pa5"
} )(function(_ref5) {
  var _ref5$shortened = _ref5.shortened, shortened = _ref5$shortened === void 0 ? false : _ref5$shortened, theme = _ref5.theme;
  return {
    height: "36px",
    width: shortened ? "100%" : "calc(100% - ".concat(MONOMER_HIDE_LIBRARY_BUTTON_WIDTH, ")"),
    marginBottom: "6px",
    display: "flex",
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    boxShadow: theme.ketcher.shadow.mainLayoutBlocks,
    borderRadius: "4px",
    overflowX: "hidden"
  };
}, "" );
var StyledArrowScrollWrapper = createStyled("div", {
  target: "e1pv9pa4"
} )("width:42px;height:36px;display:flex;position:relative;right:0;cursor:pointer;background:white;box-shadow:", function(_ref6) {
  var theme = _ref6.theme;
  return theme.ketcher.shadow.mainLayoutBlocks;
}, ";border-radius:4px;" + ("" ));
var Bottom = createStyled("div", {
  target: "e1pv9pa3"
} )({
  name: "1gavlve",
  styles: "&:not(:empty){margin-bottom:15px;}"
} );
var Main = createStyled("div", {
  target: "e1pv9pa2"
} )({
  name: "nc15h",
  styles: "height:100%;width:100%;position:relative;overflow:hidden"
} );
var InsideRoot = createStyled("div", {
  target: "e1pv9pa1"
} )({
  name: "0",
  styles: ""
} );
var DummyDiv = createStyled("div", {
  target: "e1pv9pa0"
} )({
  name: "1k18kha",
  styles: "height:40px"
} );
var Top = function Top2(props) {
  var _useInView = useInView({
    threshold: 1
  }), _useInView2 = _slicedToArray(_useInView, 2), startRef = _useInView2[0], startInView = _useInView2[1];
  var _useInView3 = useInView({
    threshold: 1
  }), _useInView4 = _slicedToArray(_useInView3, 2), endRef = _useInView4[0], endInView = _useInView4[1];
  var children2 = props.children, otherProps = _objectWithoutProperties(props, _excluded$4);
  var scrollRef = reactExports.useRef(null);
  var SCROLL_PX_PER_SEC = 300;
  var scrollRight = function scrollRight2(dtMs) {
    if (!scrollRef.current) {
      return;
    }
    scrollRef.current.scrollLeft += SCROLL_PX_PER_SEC * dtMs / 1e3;
  };
  var scrollLeft = function scrollLeft2(dtMs) {
    if (!scrollRef.current) {
      return;
    }
    scrollRef.current.scrollLeft -= SCROLL_PX_PER_SEC * dtMs / 1e3;
  };
  return jsxs("div", {
    style: {
      display: "flex",
      position: "relative"
    },
    children: [jsxs(StyledTop, _objectSpread$o(_objectSpread$o({}, otherProps), {}, {
      ref: scrollRef,
      children: [jsx("span", {
        ref: startRef
      }), jsx(StyledTopInnerDiv, {
        children: jsx(Fragment, {
          children: children2
        })
      }), jsx("span", {
        ref: endRef
      })]
    })), !startInView || !endInView ? jsx(StyledArrowScrollWrapper, {
      children: jsx(ArrowScroll, {
        startInView,
        endInView,
        scrollBack: scrollLeft,
        scrollForward: scrollRight,
        isLeftRight: true
      })
    }) : null]
  });
};
var Layout = function Layout2(_ref7) {
  var children2 = _ref7.children;
  var subcomponents = {
    Left: null,
    Main: null,
    Right: null,
    Top: null,
    Bottom: null,
    InsideRoot: null
  };
  React__default.Children.forEach(children2, function(child) {
    if (child.type === Left) {
      subcomponents.Left = child;
    } else if (child.type === Right) {
      subcomponents.Right = child;
    } else if (child.type === Top) {
      subcomponents.Top = child;
    } else if (child.type === Bottom) {
      subcomponents.Bottom = child;
    } else if (child.type === Main) {
      subcomponents.Main = child;
    } else if (child.type === InsideRoot) {
      subcomponents.InsideRoot = child;
    }
  });
  return jsxs(RowMain, {
    children: [jsxs(Column, {
      fullWidth: true,
      withPaddingRight: true,
      children: [subcomponents.Top, jsxs(Row$1, {
        children: [subcomponents.Left, jsx(DummyDiv, {}), subcomponents.Main]
      }), subcomponents.Bottom]
    }), jsx(Column, {
      children: subcomponents.Right
    }), subcomponents.InsideRoot]
  });
};
Layout.Left = Left;
Layout.Top = Top;
Layout.Bottom = Bottom;
Layout.Right = Right;
Layout.Main = Main;
Layout.InsideRoot = InsideRoot;
var styles$4 = { "tabPanelDiv": "TabPanel-module_tabPanelDiv__wMffZ", "tabPanelBox": "TabPanel-module_tabPanelBox__LY-BB" };
var TabPanel = function TabPanel2(_ref3) {
  var children2 = _ref3.children, value = _ref3.value, index = _ref3.index;
  return jsx("div", {
    className: styles$4.tabPanelDiv,
    role: "tabpanel",
    hidden: value !== index,
    id: index.toString(),
    children: value === index && jsx(Box, {
      className: styles$4.tabPanelBox,
      children: jsx(Fragment, {
        children: children2
      })
    })
  });
};
var TabPanel$1 = TabPanel;
var StyledTabs = createStyled(Tabs$2, {
  shouldForwardProp: function shouldForwardProp(propName) {
    return propName !== "isLayoutToRight";
  },
  target: "e1rrs7vg3"
} )("height:32px;min-height:32px;list-style-type:none;margin:0;padding:4px 8px 0 8px;border-bottom:", function(_ref3) {
  var theme = _ref3.theme;
  return "1px solid ".concat(theme.ketcher.color.border.primary);
}, ";overflow:unset;& .MuiTabs-scroller,& .MuiTabs-flexContainer{height:100%;overflow:unset!important;}& .MuiTabs-flexContainer{justify-content:", function(_ref22) {
  var isLayoutToRight = _ref22.isLayoutToRight;
  return isLayoutToRight ? "flex-end" : "flex-start";
}, ";padding-right:", function(_ref3) {
  var isLayoutToRight = _ref3.isLayoutToRight;
  return isLayoutToRight ? "16px" : "0";
}, ";}& .MuiTabs-indicator{display:none;}" + ("" ));
var StyledTab = createStyled(Tab, {
  shouldForwardProp: function shouldForwardProp3(propName) {
    return propName !== "isLayoutToRight";
  },
  target: "e1rrs7vg2"
} )("min-height:24px;min-width:0;position:relative;padding:7px 12px;font-size:", function(_ref4) {
  var theme = _ref4.theme;
  return theme.ketcher.font.size.regular;
}, ";text-transform:none;cursor:pointer;text-align:center;background-color:", function(_ref5) {
  var theme = _ref5.theme;
  return theme.ketcher.color.tab.regular;
}, ";color:", function(_ref6) {
  var theme = _ref6.theme;
  return theme.ketcher.color.text.light;
}, ";list-style-type:none;margin-left:1px;align-items:center;flex:", function(_ref7) {
  var isLayoutToRight = _ref7.isLayoutToRight;
  return isLayoutToRight ? void 0 : "1 1 auto;";
}, ";border:1px solid transparent;border-bottom:none;border-radius:4px 4px 0 0;&:first-of-type{margin-left:0;}&:hover{background-color:", function(_ref8) {
  var theme = _ref8.theme;
  return theme.ketcher.color.tab.regular;
}, ";color:", function(_ref9) {
  var theme = _ref9.theme;
  return theme.ketcher.color.text.primary;
}, ";border-color:", function(_ref0) {
  var theme = _ref0.theme;
  return theme.ketcher.color.border.primary;
}, ";}&.Mui-selected{background-color:", function(_ref1) {
  var theme = _ref1.theme;
  return theme.ketcher.color.tab.active;
}, ";color:", function(_ref10) {
  var theme = _ref10.theme;
  return theme.ketcher.color.text.primary;
}, ";border-color:", function(_ref11) {
  var theme = _ref11.theme;
  return theme.ketcher.color.border.primary;
}, ";margin-bottom:-1px;padding-bottom:8px;&::after{content:'';position:absolute;left:0;bottom:-1px;height:1px;background-color:", function(_ref12) {
  var theme = _ref12.theme;
  return theme.ketcher.color.tab.active;
}, ";}}&[data-tab='Favorites']{font-size:16px;color:#faa500;}" + ("" ));
var HiddenTab = createStyled(Tab, {
  target: "e1rrs7vg1"
} )({
  name: "2934o7",
  styles: "width:0;height:0;min-width:0;min-height:0;padding:0;margin:0;visibility:hidden"
} );
var TabPanelContent = createStyled("div", {
  target: "e1rrs7vg0"
} )({
  name: "2r6rpv",
  styles: "display:flex;flex-direction:row;flex-wrap:wrap;justify-content:flex-start;width:100%;height:100%"
} );
function ownKeys$n(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$n(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$n(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$n(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var a11yProps = function a11yProps2(index) {
  return {
    id: "simple-tab-".concat(index),
    "aria-controls": "simple-tabpanel-".concat(index)
  };
};
var Tabs = function Tabs2(props) {
  var tabs = props.tabs, selectedTabIndex = props.selectedTabIndex, isLayoutToRight = props.isLayoutToRight, onChange = props.onChange;
  var tabPanel = tabs[selectedTabIndex];
  var Component = tabPanel === null || tabPanel === void 0 ? void 0 : tabPanel.component;
  var componentProps = tabPanel === null || tabPanel === void 0 ? void 0 : tabPanel.props;
  return jsxs(Fragment, {
    children: [jsxs(StyledTabs, {
      value: selectedTabIndex,
      onChange,
      isLayoutToRight,
      children: [tabs.map(function(tabPanel2, index) {
        return jsx(StyledTab, _objectSpread$n({
          label: tabPanel2.caption,
          title: tabPanel2.tooltip,
          isLayoutToRight,
          "data-testid": tabPanel2.testId,
          "data-tab": tabPanel2.tooltip
        }, a11yProps(index)), tabPanel2.caption || tabPanel2.testId);
      }), jsx(HiddenTab, {
        value: -1
      })]
    }), tabPanel && jsx(TabPanel$1, {
      value: selectedTabIndex,
      index: selectedTabIndex,
      children: jsx(TabPanelContent, {
        children: jsx(Component, _objectSpread$n({}, componentProps))
      })
    })]
  });
};
var Tabs$1 = reactExports.memo(Tabs);
var EmptyFunction = function EmptyFunction2() {
};
function ownKeys$m(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$m(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$m(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$m(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var getPresets = function getPresets2(monomers, rnaPresetsTemplates, isDefault) {
  var monomerLibraryItemByMonomerIDMap = new Map(monomers.map(function(monomer) {
    var monomerID = isAmbiguousMonomerLibraryItem(monomer) ? setAmbiguousMonomerTemplatePrefix(monomer.id) : setMonomerTemplatePrefix(monomer.props.id || getMonomerUniqueKey(monomer));
    return [monomerID, monomer];
  }));
  return rnaPresetsTemplates.filter(function(rnaPresetsTemplate) {
    return rnaPresetsTemplate.templates.every(function(rnaPartsMonomerTemplateRef) {
      return Boolean(monomerLibraryItemByMonomerIDMap.get(rnaPartsMonomerTemplateRef.$ref));
    });
  }).map(function(rnaPresetsTemplate) {
    var _rnaPresetsTemplate$c;
    var rnaPartsMonomerLibraryItemByMonomerClassMap = new Map(rnaPresetsTemplate.templates.map(function(rnaPartsMonomerTemplateRef) {
      var monomer = monomerLibraryItemByMonomerIDMap.get(rnaPartsMonomerTemplateRef.$ref);
      var _monomerFactory = monomerFactory(monomer), _monomerFactory2 = _slicedToArray(_monomerFactory, 3), monomerClass = _monomerFactory2[2];
      return [monomerClass, monomer];
    }));
    var ribose = rnaPartsMonomerLibraryItemByMonomerClassMap.get(KetMonomerClass.Sugar);
    var rnaBase = rnaPartsMonomerLibraryItemByMonomerClassMap.get(KetMonomerClass.Base);
    var phosphate = rnaPartsMonomerLibraryItemByMonomerClassMap.get(KetMonomerClass.Phosphate);
    var connections = (_rnaPresetsTemplate$c = rnaPresetsTemplate.connections) !== null && _rnaPresetsTemplate$c !== void 0 ? _rnaPresetsTemplate$c : buildRnaPresetConnections({
      base: rnaBase,
      sugar: ribose,
      phosphate
    });
    var result = {
      base: rnaBase ? _objectSpread$m(_objectSpread$m({}, rnaBase), {}, {
        label: rnaBase.label
      }) : void 0,
      name: rnaPresetsTemplate.name,
      phosphate: phosphate ? _objectSpread$m(_objectSpread$m({}, phosphate), {}, {
        label: phosphate.label
      }) : void 0,
      connections,
      sugar: ribose ? _objectSpread$m(_objectSpread$m({}, ribose), {}, {
        label: ribose.label
      }) : void 0,
      phosphatePosition: getRnaPresetPhosphatePosition({
        sugar: ribose,
        phosphate,
        connections
      }),
      favorite: rnaPresetsTemplate.favorite,
      "default": isDefault || rnaPresetsTemplate["default"]
    };
    var presetWithAliases = _objectSpread$m(_objectSpread$m(_objectSpread$m({}, result), rnaPresetsTemplate.idtAliases && {
      idtAliases: rnaPresetsTemplate.idtAliases
    }), rnaPresetsTemplate.aliasAxoLabs && {
      aliasAxoLabs: rnaPresetsTemplate.aliasAxoLabs
    });
    return presetWithAliases;
  });
};
var getConnectedAttachmentPoints = function getConnectedAttachmentPoints2(bonds) {
  return Object.entries(bonds).filter(function(_ref3) {
    var _ref22 = _slicedToArray(_ref3, 2);
    _ref22[0];
    var bond = _ref22[1];
    return Boolean(bond);
  }).map(function(_ref3) {
    var _ref4 = _slicedToArray(_ref3, 1), attachmentPoint = _ref4[0];
    return attachmentPoint;
  });
};
var removeSlashesFromIdtAlias = function removeSlashesFromIdtAlias2(alias) {
  if (!alias) return alias;
  return alias.replace(/(?:^\/+)|(?:\/+$)/g, "");
};
var useAppDispatch = function useAppDispatch2() {
  return useDispatch();
};
var useAppSelector = useSelector;
function useLayoutMode() {
  var _ketcher;
  var ketcherId = useAppSelector(selectKetcherId);
  var editor = useAppSelector(selectEditor);
  var previousLayoutMode = useAppSelector(selectEditorLayoutMode);
  var ketcher;
  try {
    ketcher = ketcherProvider.getKetcher(ketcherId);
  } catch (error) {
    KetcherLogger.error("Failed to get ketcher instance with id ".concat(ketcherId), error);
  }
  var isBlank = (_ketcher = ketcher) === null || _ketcher === void 0 || (_ketcher = _ketcher.editor) === null || _ketcher === void 0 ? void 0 : _ketcher.struct().isBlank();
  var fallbackMode = isBlank ? DEFAULT_LAYOUT_MODE : HAS_CONTENT_LAYOUT_MODE;
  var _useState = reactExports.useState(previousLayoutMode || fallbackMode), _useState2 = _slicedToArray(_useState, 2), layoutMode = _useState2[0], setLayoutMode = _useState2[1];
  var onLayoutModeChange = reactExports.useCallback(function(newLayoutMode) {
    setLayoutMode(newLayoutMode);
  }, []);
  reactExports.useEffect(function() {
    editor === null || editor === void 0 || editor.events.layoutModeChange.add(onLayoutModeChange);
    return function() {
      onLayoutModeChange(DEFAULT_LAYOUT_MODE);
      editor === null || editor === void 0 || editor.events.layoutModeChange.remove(onLayoutModeChange);
    };
  }, [onLayoutModeChange, editor]);
  return layoutMode;
}
function useSequenceEditInRNABuilderMode() {
  var editor = useAppSelector(selectEditor);
  var isSequenceEditInRNABuilderModeInitial = useAppSelector(selectIsSequenceEditInRNABuilderMode);
  var _useState3 = reactExports.useState(isSequenceEditInRNABuilderModeInitial), _useState4 = _slicedToArray(_useState3, 2), isSequenceEditInRNABuilderMode = _useState4[0], setIsSequenceEditInRNABuilderMode = _useState4[1];
  var onSequenceEditInRNABuilderModeChange = reactExports.useCallback(function(value) {
    setIsSequenceEditInRNABuilderMode(value);
  }, []);
  reactExports.useEffect(function() {
    editor === null || editor === void 0 || editor.events.toggleSequenceEditInRNABuilderMode.add(onSequenceEditInRNABuilderModeChange);
    return function() {
      editor === null || editor === void 0 || editor.events.toggleSequenceEditInRNABuilderMode.remove(onSequenceEditInRNABuilderModeChange);
    };
  }, [onSequenceEditInRNABuilderModeChange, editor]);
  return isSequenceEditInRNABuilderMode;
}
var MenuContext = React__default.createContext({});
var MenuContext$1 = MenuContext;
var RootSizeContext = reactExports.createContext({
  width: 0,
  height: 0
});
var RootSizeProvider = function RootSizeProvider2(_ref3) {
  var children2 = _ref3.children, rootRef = _ref3.rootRef, isMacromoleculesEditorTurnedOn = _ref3.isMacromoleculesEditorTurnedOn;
  var _useState = reactExports.useState({
    width: 0,
    height: 0
  }), _useState2 = _slicedToArray(_useState, 2), size = _useState2[0], setSize = _useState2[1];
  var handleResize = reactExports.useCallback(function() {
    if (!(rootRef !== null && rootRef !== void 0 && rootRef.current)) {
      return;
    }
    var _rootRef$current$getB = rootRef.current.getBoundingClientRect(), width = _rootRef$current$getB.width, height = _rootRef$current$getB.height;
    setSize({
      width,
      height
    });
  }, [rootRef]);
  var debouncedHandleResize = reactExports.useCallback(lodashExports.debounce(handleResize, 100), [handleResize]);
  reactExports.useEffect(function() {
    handleResize();
  }, [isMacromoleculesEditorTurnedOn]);
  reactExports.useEffect(function() {
    debouncedHandleResize();
    window.addEventListener("resize", debouncedHandleResize);
    return function() {
      window.removeEventListener("resize", debouncedHandleResize);
    };
  }, [debouncedHandleResize]);
  return jsx(RootSizeContext.Provider, {
    value: size,
    children: children2
  });
};
var useIsCompactView = function useIsCompactView2() {
  var _useContext = reactExports.useContext(RootSizeContext), height = _useContext.height;
  return height < 720;
};
var getModificationTypeAttribute = function getModificationTypeAttribute2(modificationTypes) {
  if (!modificationTypes) {
    return void 0;
  }
  if (Array.isArray(modificationTypes)) {
    return modificationTypes.join(", ");
  }
  return modificationTypes;
};
var Card$1 = createStyled("div", {
  target: "e719szw4"
} )("background:white;height:48px;text-align:center;cursor:", function(_ref3) {
  var disabled = _ref3.disabled, isDragging = _ref3.isDragging;
  if (disabled) {
    return "default";
  }
  return isDragging ? "grabbing !important" : "pointer";
}, ";opacity:", function(_ref22) {
  var disabled = _ref22.disabled;
  return disabled ? "0.4" : "1";
}, ";display:flex;justify-content:space-between;align-items:center;font-size:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.font.size.small;
}, ";color:", function(_ref4) {
  var theme = _ref4.theme;
  return theme.ketcher.color.text.primary;
}, ";position:relative;overflow:hidden;border-radius:4px;box-shadow:0 2px 5px 0 rgba(103, 104, 132, 0.149);margin:0;user-select:none;border-color:#167782;border-width:", function(_ref5) {
  var selected = _ref5.selected;
  return selected ? "2px 2px 2px" : "0px";
}, ";border-style:solid;box-sizing:border-box;z-index:", function(_ref6) {
  var selected = _ref6.selected;
  return selected ? 2 : void 0;
}, ";", function(_ref7) {
  var isDragging = _ref7.isDragging;
  return isDragging && "\n    &, & * {\n      pointer-events: none !important;\n      cursor: grabbing !important;\n    }\n  ";
}, " .hidden & .star{visibility:hidden!important;}&:hover{outline:1px solid #b4b9d6;>.star,.autochain{visibility:visible;opacity:1;}}&::after{content:'';display:block;position:absolute;top:0;left:0;width:100%;height:8px;border-bottom:", function(_ref8) {
  var isVariantMonomer = _ref8.isVariantMonomer;
  return isVariantMonomer ? "1px solid #CAD3DD" : "none";
}, ";background:", function(_ref9) {
  var _theme$ketcher$monome, _monomerItem$props, _theme$ketcher$peptid, _theme$ketcher$monome2, _theme$ketcher$monome3;
  var code = _ref9.code, theme = _ref9.theme, item = _ref9.item;
  if (!item) return (_theme$ketcher$monome = theme.ketcher.monomer.color["default"]) === null || _theme$ketcher$monome === void 0 ? void 0 : _theme$ketcher$monome.regular;
  var monomerItem = item;
  var isPeptideTab = ((_monomerItem$props = monomerItem.props) === null || _monomerItem$props === void 0 ? void 0 : _monomerItem$props.MonomerType) === "PEPTIDE";
  if (isPeptideTab && (_theme$ketcher$peptid = theme.ketcher.peptide.color[code]) !== null && _theme$ketcher$peptid !== void 0 && _theme$ketcher$peptid.regular) {
    var _theme$ketcher$peptid2;
    return (_theme$ketcher$peptid2 = theme.ketcher.peptide.color[code]) === null || _theme$ketcher$peptid2 === void 0 ? void 0 : _theme$ketcher$peptid2.regular;
  }
  var monomerColor = ((_theme$ketcher$monome2 = theme.ketcher.monomer.color[code]) === null || _theme$ketcher$monome2 === void 0 ? void 0 : _theme$ketcher$monome2.regular) || ((_theme$ketcher$monome3 = theme.ketcher.monomer.color["default"]) === null || _theme$ketcher$monome3 === void 0 ? void 0 : _theme$ketcher$monome3.regular);
  return monomerColor;
}, ";},>span{position:absolute;bottom:", function(_ref0) {
  var selected = _ref0.selected;
  return selected ? "4px" : "6px";
}, ";left:", function(_ref1) {
  var selected = _ref1.selected;
  return selected ? "4px" : "6px";
}, ";overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:85%;}>.star{color:#cad3dd;position:absolute;left:calc(50% - 7px);top:11px;font-size:13px;line-height:13px;opacity:0;transition:0.2s ease;flex-shrink:0;border:0;background:transparent;padding:0;cursor:pointer;&.visible{visibility:visible;opacity:1;}&:active{transform:scale(1.4);}&:hover,&.visible{color:#faa500;}}" + ("" ));
var NumberCircle = createStyled("div", {
  target: "e719szw3"
} )("display:flex;justify-content:center;align-items:center;height:15px;width:", function(_ref10) {
  var monomersAmount = _ref10.monomersAmount;
  return monomersAmount >= 10 ? "20px" : "15px";
}, ";border-radius:", function(_ref11) {
  var monomersAmount = _ref11.monomersAmount;
  return monomersAmount >= 10 ? "20px" : "50%";
}, ";border:1px solid #cceaee;position:absolute;bottom:", function(_ref12) {
  var selected = _ref12.selected;
  return selected ? "4px" : "6px";
}, ";left:", function(_ref13) {
  var selected = _ref13.selected;
  return selected ? "18px" : "20px";
}, ";font-size:12px;line-height:12px;" + ("" ));
var CardTitle = createStyled("span", {
  target: "e719szw2"
} )({
  name: "rnnx2x",
  styles: "font-size:12px"
} );
var AutochainIcon = createStyled(Icon, {
  target: "e719szw1"
} )("color:#cad3dd;stroke-width:0;opacity:0;transition:0.2s ease;flex-shrink:0;width:13px;&:active{transform:scale(1.2);}&:hover{color:", function(_ref14) {
  var disabled = _ref14.disabled;
  return disabled ? "#cad3dd" : "#333333";
}, ";}" + ("" ));
var AutochainIconWrapper = createStyled("div", {
  target: "e719szw0"
} )({
  name: "evdt6m",
  styles: "position:absolute;top:12px;left:4px"
} );
var useDisabledForSequenceMode = function useDisabledForSequenceMode2(item, groupName) {
  var _item$props9, _item$props0, _item$props1;
  var isSequenceEditInRNABuilderMode = useAppSelector(selectIsSequenceEditInRNABuilderMode);
  var isSequenceFirstsOnlyNucleoelementsSelected = useSelector(selectIsSequenceFirstsOnlyNucleotidesSelected);
  var _useState = reactExports.useState(false), _useState2 = _slicedToArray(_useState, 2), isDisabled = _useState2[0], setIsDisabled = _useState2[1];
  reactExports.useEffect(function() {
    if (!isSequenceEditInRNABuilderMode) return setIsDisabled(false);
    if (groupName === MonomerGroups$1.BASES) {
      var _item$props;
      setIsDisabled(!(item !== null && item !== void 0 && (_item$props = item.props) !== null && _item$props !== void 0 && (_item$props = _item$props.MonomerCaps) !== null && _item$props !== void 0 && _item$props.R1));
    } else if (groupName === MonomerGroups$1.PHOSPHATES) {
      var _item$props2, _item$props3;
      setIsDisabled(!(item !== null && item !== void 0 && (_item$props2 = item.props) !== null && _item$props2 !== void 0 && (_item$props2 = _item$props2.MonomerCaps) !== null && _item$props2 !== void 0 && _item$props2.R1 && item !== null && item !== void 0 && (_item$props3 = item.props) !== null && _item$props3 !== void 0 && (_item$props3 = _item$props3.MonomerCaps) !== null && _item$props3 !== void 0 && _item$props3.R2));
    } else if (groupName === MonomerGroups$1.SUGARS) {
      if (isSequenceFirstsOnlyNucleoelementsSelected) {
        var _item$props4, _item$props5;
        setIsDisabled(!(item !== null && item !== void 0 && (_item$props4 = item.props) !== null && _item$props4 !== void 0 && (_item$props4 = _item$props4.MonomerCaps) !== null && _item$props4 !== void 0 && _item$props4.R3 && item !== null && item !== void 0 && (_item$props5 = item.props) !== null && _item$props5 !== void 0 && (_item$props5 = _item$props5.MonomerCaps) !== null && _item$props5 !== void 0 && _item$props5.R2));
      } else {
        var _item$props6, _item$props7, _item$props8;
        setIsDisabled(!(item !== null && item !== void 0 && (_item$props6 = item.props) !== null && _item$props6 !== void 0 && (_item$props6 = _item$props6.MonomerCaps) !== null && _item$props6 !== void 0 && _item$props6.R3 && item !== null && item !== void 0 && (_item$props7 = item.props) !== null && _item$props7 !== void 0 && (_item$props7 = _item$props7.MonomerCaps) !== null && _item$props7 !== void 0 && _item$props7.R2 && item !== null && item !== void 0 && (_item$props8 = item.props) !== null && _item$props8 !== void 0 && (_item$props8 = _item$props8.MonomerCaps) !== null && _item$props8 !== void 0 && _item$props8.R1));
      }
    }
  }, [groupName, isSequenceEditInRNABuilderMode, isSequenceFirstsOnlyNucleoelementsSelected, item === null || item === void 0 || (_item$props9 = item.props) === null || _item$props9 === void 0 || (_item$props9 = _item$props9.MonomerCaps) === null || _item$props9 === void 0 ? void 0 : _item$props9.R1, item === null || item === void 0 || (_item$props0 = item.props) === null || _item$props0 === void 0 || (_item$props0 = _item$props0.MonomerCaps) === null || _item$props0 === void 0 ? void 0 : _item$props0.R2, item === null || item === void 0 || (_item$props1 = item.props) === null || _item$props1 === void 0 || (_item$props1 = _item$props1.MonomerCaps) === null || _item$props1 === void 0 ? void 0 : _item$props1.R3, setIsDisabled]);
  return isDisabled;
};
var useDisabledForSequenceMode$1 = useDisabledForSequenceMode;
var useLibraryItemDrag = function useLibraryItemDrag2(item, itemRef) {
  var editor = useSelector(selectEditor);
  var dispatch2 = useDispatch();
  reactExports.useEffect(function() {
    if (!editor || !itemRef.current) {
      return;
    }
    var itemElement = select(itemRef.current);
    var dragBehavior = drag().on("start", function() {
      editor.isLibraryItemDragCancelled = editor.mode.modeName === "sequence-layout-mode";
      if (!editor.isLibraryItemDragCancelled) {
        document.body.style.cursor = "grabbing";
      }
    }).on("drag", function(event) {
      var _editor$ketcherRootEl, _editor$ketcherRootEl2;
      if (editor.isLibraryItemDragCancelled) {
        return;
      }
      dispatch2(setIsDragging2(true));
      var _event$sourceEvent = event.sourceEvent, x2 = _event$sourceEvent.clientX, y2 = _event$sourceEvent.clientY;
      editor.events.setLibraryItemDragState.dispatch({
        item,
        position: {
          x: x2 - (((_editor$ketcherRootEl = editor.ketcherRootElementBoundingClientRect) === null || _editor$ketcherRootEl === void 0 ? void 0 : _editor$ketcherRootEl.left) || 0),
          y: y2 - (((_editor$ketcherRootEl2 = editor.ketcherRootElementBoundingClientRect) === null || _editor$ketcherRootEl2 === void 0 ? void 0 : _editor$ketcherRootEl2.top) || 0)
        }
      });
    }).on("end", function(event) {
      if (!editor.isLibraryItemDragCancelled) {
        var _ZoomTool$instance$ca;
        var _event$sourceEvent2 = event.sourceEvent, x2 = _event$sourceEvent2.clientX, y2 = _event$sourceEvent2.clientY;
        var canvasWrapperBoundingClientRect = (_ZoomTool$instance$ca = ZoomTool.instance.canvasWrapper.node()) === null || _ZoomTool$instance$ca === void 0 ? void 0 : _ZoomTool$instance$ca.getBoundingClientRect();
        if (canvasWrapperBoundingClientRect) {
          var top2 = canvasWrapperBoundingClientRect.top, left2 = canvasWrapperBoundingClientRect.left, right2 = canvasWrapperBoundingClientRect.right, bottom2 = canvasWrapperBoundingClientRect.bottom;
          var transform = ZoomTool.instance.zoomTransform;
          var adjustedX = x2 - left2 + transform.k * 15;
          var adjustedY = y2 - top2 + transform.k * 15;
          var _transform$invert = transform.invert([adjustedX, adjustedY]), _transform$invert2 = _slicedToArray(_transform$invert, 2), scaledX = _transform$invert2[0], scaledY = _transform$invert2[1];
          var mouseWithinCanvas = x2 >= left2 && x2 <= right2 && y2 >= top2 && y2 <= bottom2;
          if (mouseWithinCanvas) {
            editor.events.placeLibraryItemOnCanvas.dispatch(item, {
              x: scaledX,
              y: scaledY
            });
          }
        }
      }
      editor.events.setLibraryItemDragState.dispatch(null);
      editor.isLibraryItemDragCancelled = false;
      document.body.style.cursor = "";
      dispatch2(setIsDragging2(false));
    });
    itemElement.call(dragBehavior);
    return function() {
      itemElement.on(".drag", null);
    };
  }, [editor, item, itemRef, dispatch2]);
};
var getAutochainErrorMessage = function getAutochainErrorMessage2(editor, libraryItem) {
  var _editor$getDataForAut = editor.getDataForAutochain(), selectedMonomersWithFreeR2 = _editor$getDataForAut.selectedMonomersWithFreeR2, selectedMonomers = _editor$getDataForAut.selectedMonomers;
  if (selectedMonomers.length > 0 && selectedMonomersWithFreeR2.length !== 1) {
    return "Select a monomer or a chain that has one R2 available.";
  }
  if (selectedMonomersWithFreeR2.length === 1 && !libraryItemHasR1AttachmentPoint(libraryItem)) {
    return "This monomer cannot be added to a chain using this button, as it lacks R1.";
  }
  return "";
};
var cardMouseOverHandler = function cardMouseOverHandler2(editor, libraryItem, setAutochainErrorMessage) {
  var errorMessage = getAutochainErrorMessage(editor, libraryItem);
  setAutochainErrorMessage(errorMessage);
};
function ownKeys$l(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$l(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$l(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$l(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var AUTOCHAIN_ELEMENT_CLASSNAME = "autochain";
var MonomerItem = function MonomerItem2(_ref3) {
  var _monomerItem$props$id, _monomerItem$props$id2, _monomerItem$props$id3, _monomerItem$props$id4, _monomerItem$props$id5, _monomerItem$props$id6, _monomerItem$props$id7, _monomerItem$props$id8, _monomerItem$props$al, _monomerItem$props$al2, _monomerItem$props$al3;
  var item = _ref3.item, groupName = _ref3.groupName, onMouseLeave = _ref3.onMouseLeave, onMouseMove = _ref3.onMouseMove, isSelected = _ref3.isSelected, disabled = _ref3.disabled, _ref$onClick = _ref3.onClick, onClick = _ref$onClick === void 0 ? EmptyFunction : _ref$onClick;
  var dispatch2 = useAppDispatch();
  var editor = useAppSelector(selectEditor);
  var isSequenceMode = useAppSelector(selectIsSequenceMode);
  var isDragging = useAppSelector(selectIsDragging);
  var _useState = reactExports.useState(""), _useState2 = _slicedToArray(_useState, 2), autochainErrorMessage = _useState2[0], setAutochainErrorMessage = _useState2[1];
  var cardRef = reactExports.useRef(null);
  var isDisabled = useDisabledForSequenceMode$1(item, groupName) || disabled;
  var colorCode = "";
  if (!isAmbiguousMonomerLibraryItem(item)) {
    colorCode = item.props.MonomerType === MONOMER_TYPES.CHEM ? item.props.MonomerType : item.props.MonomerNaturalAnalogCode;
  }
  var monomerKey = getMonomerUniqueKey(item);
  var monomerItem = isAmbiguousMonomerLibraryItem(item) ? void 0 : item;
  var addFavorite = reactExports.useCallback(function(event) {
    event.stopPropagation();
    dispatch2(toggleMonomerFavorites2(item));
  }, [dispatch2, item]);
  var onAutochainIconClick = reactExports.useCallback(function(event) {
    event.stopPropagation();
    if (editor) {
      var errorMessage = getAutochainErrorMessage(editor, item);
      setAutochainErrorMessage(errorMessage);
      if (errorMessage) {
        return;
      }
    }
    editor === null || editor === void 0 || editor.events.autochain.dispatch(item);
  }, [editor, item]);
  var onMouseOver = reactExports.useCallback(function() {
    return editor && cardMouseOverHandler(editor, item, setAutochainErrorMessage);
  }, [editor, item]);
  var onAutochainIconMouseOver = reactExports.useCallback(function() {
    if (editor) {
      var errorMessage = getAutochainErrorMessage(editor, item);
      setAutochainErrorMessage(errorMessage);
      if (errorMessage) {
        return;
      }
    }
    editor === null || editor === void 0 || editor.events.previewAutochain.dispatch(item);
  }, [editor, item]);
  var onAutochainIconMouseOut = reactExports.useCallback(function() {
    editor === null || editor === void 0 || editor.events.removeAutochainPreview.dispatch(item);
  }, [editor, item]);
  useLibraryItemDrag(item, cardRef);
  return jsxs(Card$1, _objectSpread$l(_objectSpread$l({
    selected: isSelected,
    disabled: isDisabled,
    isDragging,
    "data-testid": monomerKey,
    "data-monomer-item-id": monomerKey,
    item: monomerItem,
    isVariantMonomer: item.isAmbiguous,
    code: colorCode,
    onMouseOver,
    onMouseLeave,
    onMouseMove,
    onDoubleClick: function onDoubleClick(e) {
      onAutochainIconClick(e);
      onAutochainIconMouseOut();
    }
  }, !isDisabled ? {
    onClick
  } : {}), {}, {
    ref: cardRef,
    "data-idtalias-base": (_monomerItem$props$id = monomerItem === null || monomerItem === void 0 || (_monomerItem$props$id2 = monomerItem.props.idtAliases) === null || _monomerItem$props$id2 === void 0 ? void 0 : _monomerItem$props$id2.base) !== null && _monomerItem$props$id !== void 0 ? _monomerItem$props$id : void 0,
    "data-idtalias-modifications-endpoint5": (_monomerItem$props$id3 = monomerItem === null || monomerItem === void 0 || (_monomerItem$props$id4 = monomerItem.props.idtAliases) === null || _monomerItem$props$id4 === void 0 || (_monomerItem$props$id4 = _monomerItem$props$id4.modifications) === null || _monomerItem$props$id4 === void 0 ? void 0 : _monomerItem$props$id4.endpoint5) !== null && _monomerItem$props$id3 !== void 0 ? _monomerItem$props$id3 : void 0,
    "data-idtalias-modifications-endpoint3": (_monomerItem$props$id5 = monomerItem === null || monomerItem === void 0 || (_monomerItem$props$id6 = monomerItem.props.idtAliases) === null || _monomerItem$props$id6 === void 0 || (_monomerItem$props$id6 = _monomerItem$props$id6.modifications) === null || _monomerItem$props$id6 === void 0 ? void 0 : _monomerItem$props$id6.endpoint3) !== null && _monomerItem$props$id5 !== void 0 ? _monomerItem$props$id5 : void 0,
    "data-idtalias-modifications-internal": (_monomerItem$props$id7 = monomerItem === null || monomerItem === void 0 || (_monomerItem$props$id8 = monomerItem.props.idtAliases) === null || _monomerItem$props$id8 === void 0 || (_monomerItem$props$id8 = _monomerItem$props$id8.modifications) === null || _monomerItem$props$id8 === void 0 ? void 0 : _monomerItem$props$id8.internal) !== null && _monomerItem$props$id7 !== void 0 ? _monomerItem$props$id7 : void 0,
    "data-axolabs": (_monomerItem$props$al = monomerItem === null || monomerItem === void 0 ? void 0 : monomerItem.props.aliasAxoLabs) !== null && _monomerItem$props$al !== void 0 ? _monomerItem$props$al : void 0,
    "data-helm": (_monomerItem$props$al2 = monomerItem === null || monomerItem === void 0 ? void 0 : monomerItem.props.aliasHELM) !== null && _monomerItem$props$al2 !== void 0 ? _monomerItem$props$al2 : void 0,
    "data-biln": (_monomerItem$props$al3 = monomerItem === null || monomerItem === void 0 ? void 0 : monomerItem.props.aliasBILN) !== null && _monomerItem$props$al3 !== void 0 ? _monomerItem$props$al3 : void 0,
    "data-modificationtype": getModificationTypeAttribute(monomerItem === null || monomerItem === void 0 ? void 0 : monomerItem.props.modificationTypes),
    children: [jsx(CardTitle, {
      children: item.label
    }), !isDisabled && jsxs(Fragment, {
      children: [!isSequenceMode && jsx(Tooltip, {
        title: autochainErrorMessage,
        children: jsx(AutochainIconWrapper, {
          children: jsx(AutochainIcon, {
            className: AUTOCHAIN_ELEMENT_CLASSNAME,
            name: "monomer-autochain",
            disabled: Boolean(autochainErrorMessage),
            onMouseOver: onAutochainIconMouseOver,
            onMouseOut: onAutochainIconMouseOut,
            onClick: onAutochainIconClick,
            onDoubleClick: function onDoubleClick(e) {
              return e.stopPropagation();
            }
          })
        })
      }), jsx("button", {
        type: "button",
        onClick: addFavorite,
        className: "star ".concat(item.favorite ? "visible" : ""),
        "aria-label": "Toggle favorite",
        children: FavoriteStarSymbol
      })]
    }), isAmbiguousMonomerLibraryItem(item) && jsx(NumberCircle, {
      selected: isSelected,
      monomersAmount: item.monomers.length,
      children: item.monomers.length
    })]
  }));
};
var ItemsContainer = createStyled("div", {
  target: "e10tnh3n3"
} )({
  name: "37420",
  styles: "display:grid;grid-template-columns:repeat(3, 1fr);grid-template-rows:auto;flex:1;gap:4px;&::after{content:'';flex:auto;}"
} );
var GroupContainerRow = createStyled("div", {
  target: "e10tnh3n2"
} )("position:relative;display:flex;flex-direction:row;flex-wrap:wrap;justify-content:flex-start;font-size:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.font.size.small;
}, ";font-family:", function(_ref22) {
  var theme = _ref22.theme;
  return theme.ketcher.font.family.roboto;
}, ";color:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.color.divider;
}, ";margin:0;gap:4px;" + ("" ));
var GroupContainerColumn = createStyled(GroupContainerRow, {
  target: "e10tnh3n1"
} )({
  name: "qdeacm",
  styles: "flex-direction:column"
} );
var GroupTitle = createStyled("div", {
  target: "e10tnh3n0"
} )("height:100%;display:flex;flex-grow:0;flex-basis:14px;flex-direction:column;flex-wrap:wrap;justify-content:flex-start;font-size:", function(_ref4) {
  var theme = _ref4.theme;
  return theme.ketcher.font.size.medium;
}, ";font-family:", function(_ref5) {
  var theme = _ref5.theme;
  return theme.ketcher.font.family.roboto;
}, ";color:", function(_ref6) {
  var theme = _ref6.theme;
  return theme.ketcher.color.text.primary;
}, ";margin:0;" + ("" ));
var classNamesToSkipPreview = [AUTOCHAIN_ELEMENT_CLASSNAME];
var needSkipPreviewForElement = function needSkipPreviewForElement2(element) {
  return classNamesToSkipPreview.some(function(className) {
    return element.classList.contains(className) || element.closest(".".concat(className));
  });
};
function _createForOfIteratorHelper$5(r, e) {
  var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"];
  if (!t) {
    if (Array.isArray(r) || (t = _unsupportedIterableToArray$5(r)) || e) {
      t && (r = t);
      var _n = 0, F = function F2() {
      };
      return { s: F, n: function n() {
        return _n >= r.length ? { done: true } : { done: false, value: r[_n++] };
      }, e: function e3(r2) {
        throw r2;
      }, f: F };
    }
    throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.");
  }
  var o, a = true, u = false;
  return { s: function s() {
    t = t.call(r);
  }, n: function n() {
    var r2 = t.next();
    return a = r2.done, r2;
  }, e: function e3(r2) {
    u = true, o = r2;
  }, f: function f() {
    try {
      a || null == t["return"] || t["return"]();
    } finally {
      if (u) throw o;
    }
  } };
}
function _unsupportedIterableToArray$5(r, a) {
  if (r) {
    if ("string" == typeof r) return _arrayLikeToArray$5(r, a);
    var t = {}.toString.call(r).slice(8, -1);
    return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray$5(r, a) : void 0;
  }
}
function _arrayLikeToArray$5(r, a) {
  (null == a || a > r.length) && (a = r.length);
  for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e];
  return n;
}
var MonomerGroup = function MonomerGroup2(_ref3) {
  var items = _ref3.items, title = _ref3.title, groupName = _ref3.groupName, selectedMonomerUniqueKey = _ref3.selectedMonomerUniqueKey, libraryName = _ref3.libraryName, disabled = _ref3.disabled, _ref$onItemClick = _ref3.onItemClick, onItemClick = _ref$onItemClick === void 0 ? EmptyFunction : _ref$onItemClick;
  var dispatch2 = useAppDispatch();
  var editor = useAppSelector(selectEditor);
  var activeGroupItemValidations = useAppSelector(selectGroupItemValidations);
  var isMonomerDisabled = function isMonomerDisabled2(monomer) {
    var monomerDisabled = false;
    if (isAmbiguousMonomerLibraryItem(monomer)) {
      return false;
    }
    if (disabled) {
      monomerDisabled = disabled;
    } else {
      var _monomer$props, _monomer$props2;
      var monomerValidations = activeGroupItemValidations["".concat((_monomer$props = monomer.props) === null || _monomer$props === void 0 ? void 0 : _monomer$props.MonomerClass, "s")];
      if ((monomerValidations === null || monomerValidations === void 0 ? void 0 : monomerValidations.length) > 0 && (_monomer$props2 = monomer.props) !== null && _monomer$props2 !== void 0 && _monomer$props2.MonomerCaps) {
        var _iterator = _createForOfIteratorHelper$5(monomerValidations), _step;
        try {
          for (_iterator.s(); !(_step = _iterator.n()).done; ) {
            var monomerValidation = _step.value;
            if (!(monomerValidation in monomer.props.MonomerCaps)) {
              monomerDisabled = true;
            }
          }
        } catch (err) {
          _iterator.e(err);
        } finally {
          _iterator.f();
        }
      }
    }
    return monomerDisabled;
  };
  var dispatchShowPreview = reactExports.useCallback(function(payload) {
    return dispatch2(showPreview2(payload));
  }, [dispatch2]);
  var debouncedShowPreview = reactExports.useCallback(lodashExports.debounce(function(p) {
    return dispatchShowPreview(p);
  }, 500), [dispatchShowPreview]);
  var handleItemMouseLeave = function handleItemMouseLeave2() {
    debouncedShowPreview.cancel();
    dispatch2(showPreview2(void 0));
  };
  var handleItemMouseMove = function handleItemMouseMove2(monomer, e) {
    handleItemMouseLeave();
    if (needSkipPreviewForElement(e.target)) {
      return;
    }
    var cardCoordinates = e.currentTarget.getBoundingClientRect();
    var style;
    var previewType;
    var top2;
    if (isAmbiguousMonomerLibraryItem(monomer)) {
      top2 = monomer ? calculateAmbiguousMonomerPreviewTop(monomer)(cardCoordinates) : "";
      var left2 = "".concat(cardCoordinates.left + cardCoordinates.width / 2, "px");
      previewType = PreviewType.AmbiguousMonomer;
      style = {
        left: left2,
        top: top2,
        transform: "translate(-50%, 0)"
      };
    } else {
      top2 = monomer ? calculateMonomerPreviewTop(cardCoordinates) : "";
      style = {
        right: "-88px",
        top: top2,
        transform: "translate(-50%, 0)"
      };
      previewType = PreviewType.Monomer;
    }
    var previewData = {
      type: previewType,
      monomer,
      style
    };
    debouncedShowPreview(previewData);
  };
  var selectMonomer = function selectMonomer2(monomer) {
    if (["FAVORITES", "PEPTIDE", "CHEM"].includes(libraryName !== null && libraryName !== void 0 ? libraryName : "")) {
      editor === null || editor === void 0 || editor.events.selectMonomer.dispatch(monomer);
    }
    onItemClick(monomer);
  };
  var isMonomerSelected = function isMonomerSelected2(monomer) {
    return selectedMonomerUniqueKey === getMonomerUniqueKey(monomer);
  };
  if (!items || items.length === 0) {
    return null;
  }
  return jsxs(GroupContainerColumn, {
    children: [title && jsx(GroupTitle, {
      children: title
    }), jsx(ItemsContainer, {
      children: items.map(function(monomer) {
        return jsx(MonomerItem, {
          disabled: isMonomerDisabled(monomer),
          item: monomer,
          groupName,
          isSelected: isMonomerSelected(monomer),
          onMouseLeave: handleItemMouseLeave,
          onMouseMove: function onMouseMove(e) {
            return handleItemMouseMove(monomer, e);
          },
          onClick: function onClick() {
            return selectMonomer(monomer);
          }
        }, getMonomerUniqueKey(monomer));
      })
    })]
  });
};
var MonomerListContainer = createStyled("div", {
  target: "e1bp6il60"
} )({
  name: "8z91a1",
  styles: "width:100%;display:flex;flex-direction:column;justify-items:center;gap:8px;padding:8px"
} );
var Card = createStyled(Card$1, {
  target: "e1txcvj90"
} )("&::after{content:'';background:", function(_ref3) {
  var theme = _ref3.theme, selected = _ref3.selected;
  return selected ? theme.ketcher.color.button.primary.active : "#faa500";
}, ";}.dots{visibility:hidden;position:absolute;right:2px;top:10px;}&:hover .dots{visibility:visible;}>.star{right:0;left:calc(50% - 7px);top:11px;width:min-content;}" + ("" ));
var SummaryContainer = createStyled("div", {
  target: "e1h0dkll2"
} )(function(props) {
  return {
    minHeight: "32px",
    display: "flex",
    alignItems: "center",
    padding: "8px 12px",
    gap: "8px",
    borderBottom: props.theme.ketcher.border.small
  };
}, "" );
var SummaryText = createStyled("span", {
  target: "e1h0dkll1"
} )(function(props) {
  return {
    flexGrow: 1,
    fontSize: props.theme.ketcher.font.size.regular
  };
}, "" );
var StyledIcon$2 = createStyled(Icon, {
  target: "e1h0dkll0"
} )(function(props) {
  return {
    width: "16px",
    height: "16px",
    color: props.theme.ketcher.color.icon.grey,
    transition: props.theme.ketcher.transition.regular,
    transform: props.expanded ? "rotate(180deg)" : "none"
  };
}, "" );
var RnaPresetItem = function RnaPresetItem2(_ref3) {
  var preset = _ref3.preset, isSelected = _ref3.isSelected, _ref$onClick = _ref3.onClick, onClick = _ref$onClick === void 0 ? EmptyFunction : _ref$onClick, _ref$onContextMenu = _ref3.onContextMenu, onContextMenu = _ref$onContextMenu === void 0 ? EmptyFunction : _ref$onContextMenu, _ref$onMouseLeave = _ref3.onMouseLeave, onMouseLeave = _ref$onMouseLeave === void 0 ? EmptyFunction : _ref$onMouseLeave, _ref$onMouseMove = _ref3.onMouseMove, onMouseMove = _ref$onMouseMove === void 0 ? EmptyFunction : _ref$onMouseMove;
  var dispatch2 = useAppDispatch();
  var editor = useAppSelector(selectEditor);
  var isSequenceMode = useAppSelector(selectIsSequenceMode);
  var isDragging = useAppSelector(selectIsDragging);
  var _useState = reactExports.useState(""), _useState2 = _slicedToArray(_useState, 2), autochainErrorMessage = _useState2[0], setAutochainErrorMessage = _useState2[1];
  var cardRef = reactExports.useRef(null);
  var addFavorite = reactExports.useCallback(function(event) {
    event.stopPropagation();
    dispatch2(togglePresetFavorites2(preset));
  }, [dispatch2, preset]);
  var onAutochainIconClick = reactExports.useCallback(function(event) {
    event.stopPropagation();
    if (autochainErrorMessage) {
      return;
    }
    editor === null || editor === void 0 || editor.events.autochain.dispatch(preset);
  }, [autochainErrorMessage, editor, preset]);
  var onMouseOver = reactExports.useCallback(function() {
    return editor && cardMouseOverHandler(editor, preset, setAutochainErrorMessage);
  }, [editor, preset]);
  var onAutochainIconMouseOver = reactExports.useCallback(function() {
    if (autochainErrorMessage) {
      return;
    }
    editor === null || editor === void 0 || editor.events.previewAutochain.dispatch(preset);
  }, [autochainErrorMessage, editor, preset]);
  var onAutochainIconMouseOut = reactExports.useCallback(function() {
    editor === null || editor === void 0 || editor.events.removeAutochainPreview.dispatch(preset);
  }, [editor, preset]);
  useLibraryItemDrag(preset, cardRef);
  return jsxs(Card, {
    "data-testid": getPresetUniqueKey(preset),
    onClick,
    onContextMenu,
    onMouseOver,
    onMouseLeave,
    onMouseMove,
    onDoubleClick: function onDoubleClick(e) {
      onAutochainIconClick(e);
      onAutochainIconMouseOut();
    },
    selected: isSelected,
    isDragging,
    code: preset.name,
    "data-rna-preset-item-name": preset.name,
    ref: cardRef,
    children: [!isSequenceMode && jsx(Tooltip, {
      title: autochainErrorMessage,
      children: jsx(AutochainIconWrapper, {
        children: jsx(AutochainIcon, {
          className: AUTOCHAIN_ELEMENT_CLASSNAME,
          name: "monomer-autochain",
          disabled: Boolean(autochainErrorMessage),
          onMouseOver: onAutochainIconMouseOver,
          onMouseOut: onAutochainIconMouseOut,
          onClick: onAutochainIconClick,
          onDoubleClick: function onDoubleClick(e) {
            return e.stopPropagation();
          }
        })
      })
    }), jsx("span", {
      children: preset.name
    }), jsx(StyledIcon$2, {
      name: "vertical-dots",
      className: "dots",
      onClick: onContextMenu
    }), jsx("div", {
      "aria-hidden": true,
      onClick: addFavorite,
      className: "star ".concat(preset.favorite ? "visible" : ""),
      children: FavoriteStarSymbol
    })]
  });
};
var RnaPresetItem$1 = reactExports.memo(RnaPresetItem);
var CONTEXT_MENU_ID;
(function(CONTEXT_MENU_ID2) {
  CONTEXT_MENU_ID2["FOR_RNA"] = "context-menu-for-RNA";
  CONTEXT_MENU_ID2["FOR_SEQUENCE"] = "context-menu-for-sequence";
  CONTEXT_MENU_ID2["FOR_POLYMER_BOND"] = "context-menu-for-polymer-bond";
  CONTEXT_MENU_ID2["FOR_SELECTED_MONOMERS"] = "context-menu-for-selected-monomers";
})(CONTEXT_MENU_ID || (CONTEXT_MENU_ID = {}));
var StyledMenu = createStyled(it, {
  target: "ekj16lc0"
} )("--contexify-activeItem-bgColor:rgba(243, 245, 247, 1);--contexify-menu-minWidth:140px;--contexify-activeItem-color:rgba(51, 51, 51, 1);--contexify-menu-padding:4px;--contexify-itemContent-padding:6px 8px;--contexify-separator-margin:4px 0;--contexify-separator-color:#e1e5ea;.contexify_itemContent{font-family:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.font.family.inter;
}, ";font-size:", function(_ref22) {
  var theme = _ref22.theme;
  return theme.ketcher.font.size.regular;
}, ";height:28px;}.contexify_item-title{opacity:1;font-weight:bold;background:#e1e5ea;margin:-4px 0 4px -4px;width:calc(100% + 8px);border-radius:4px 4px 0 0;}.context_menu-icon{width:16px;height:16px;display:flex;align-items:center;margin-right:4px;}.context_menu-text{display:flex;align-items:center;line-height:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.font.size.regular;
}, ";}.context_menu-delete-text{display:flex;align-items:center;line-height:", function(_ref4) {
  var theme = _ref4.theme;
  return theme.ketcher.font.size.regular;
}, ";margin-left:-3px;}" + ("" ));
var assembleMenuItems = function assembleMenuItems2(menuItems, handleMenuChange) {
  var MENU_CLOSING_TIME = 500;
  var isMouseOverThrottling = false;
  var items = [];
  menuItems.forEach(function(_ref3) {
    var name = _ref3.name, title = _ref3.title, icon = _ref3.icon, hidden = _ref3.hidden, disabled = _ref3.disabled, isMenuTitle = _ref3.isMenuTitle, separator = _ref3.separator, subMenuItems = _ref3.subMenuItems, _onMouseOver = _ref3.onMouseOver, _onMouseOut = _ref3.onMouseOut;
    var item = subMenuItems !== null && subMenuItems !== void 0 && subMenuItems.length ? jsx(Kt, {
      label: title,
      "data-testid": name,
      children: assembleMenuItems2(subMenuItems, handleMenuChange)
    }, name) : jsxs(pt, {
      id: name,
      onClick: function onClick(params) {
        isMouseOverThrottling = true;
        setTimeout(function() {
          isMouseOverThrottling = false;
        }, MENU_CLOSING_TIME);
        handleMenuChange(params);
      },
      "data-testid": name,
      hidden,
      disabled,
      className: isMenuTitle ? "contexify_item-title" : "",
      onMouseOver: function onMouseOver() {
        if (isMouseOverThrottling) {
          return;
        }
        _onMouseOver === null || _onMouseOver === void 0 || _onMouseOver(name);
      },
      onMouseOut: function onMouseOut() {
        return _onMouseOut === null || _onMouseOut === void 0 ? void 0 : _onMouseOut(name);
      },
      children: [icon && jsx("span", {
        className: "context_menu-icon",
        children: icon
      }), jsx("span", {
        className: name === "delete" ? "context_menu-delete-text" : "context_menu-text",
        children: title
      })]
    }, name);
    items.push(item);
    if (separator) {
      items.push(jsx(Et, {}, "separator-".concat(name)));
    }
  });
  return items;
};
var ContextMenu = function ContextMenu2(_ref22) {
  var id2 = _ref22.id, handleMenuChange = _ref22.handleMenuChange, menuItems = _ref22.menuItems;
  var dispatch2 = useAppDispatch();
  var isContextMenuActive = useAppSelector(selectIsContextMenuActive);
  reactExports.useEffect(function() {
    var handleContextMenuClose = function handleContextMenuClose2(e) {
      var _e$target, _e$target2;
      var isClickOnNucleotide = ((_e$target = e.target) === null || _e$target === void 0 || (_e$target = _e$target.__data__) === null || _e$target === void 0 ? void 0 : _e$target.node) || ((_e$target2 = e.target) === null || _e$target2 === void 0 || (_e$target2 = _e$target2.__data__) === null || _e$target2 === void 0 ? void 0 : _e$target2.monomer);
      if (isClickOnNucleotide) {
        e.stopPropagation();
        return;
      }
      dispatch2(setContextMenuActive2(false));
    };
    document.addEventListener("click", handleContextMenuClose);
    document.addEventListener("contextmenu", handleContextMenuClose);
    return function() {
      document.removeEventListener("click", handleContextMenuClose);
      document.removeEventListener("contextmenu", handleContextMenuClose);
    };
  }, [dispatch2, id2]);
  reactExports.useEffect(function() {
    var handleEscapeKeyDown = function handleEscapeKeyDown2(event) {
      if (event.key !== "Escape" || !isContextMenuActive) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      A.hideAll();
      dispatch2(setContextMenuActive2(false));
    };
    document.addEventListener("keydown", handleEscapeKeyDown, true);
    return function() {
      document.removeEventListener("keydown", handleEscapeKeyDown, true);
    };
  }, [dispatch2, isContextMenuActive]);
  return jsx(StyledMenu, {
    id: id2,
    children: assembleMenuItems(menuItems, handleMenuChange)
  });
};
var RNAContextMenu = function RNAContextMenu2() {
  var RNA_TAB_INDEX = LIBRARY_TAB_INDEX.RNA;
  var dispatch2 = useAppDispatch();
  var activePresetForContextMenu = useAppSelector(selectActivePresetForContextMenu);
  var selectedTabIndex = useAppSelector(selectCurrentTabIndex);
  var isSequenceEditInRNABuilderMode = useAppSelector(selectIsSequenceEditInRNABuilderMode);
  var RNAMenus = [{
    name: "duplicateandedit",
    title: "Duplicate and Edit...",
    disabled: false
  }, {
    name: "edit",
    title: "Edit...",
    separator: true,
    disabled: activePresetForContextMenu === null || activePresetForContextMenu === void 0 ? void 0 : activePresetForContextMenu["default"]
  }, {
    name: "deletepreset",
    title: "Delete Preset",
    disabled: activePresetForContextMenu === null || activePresetForContextMenu === void 0 ? void 0 : activePresetForContextMenu["default"]
  }];
  var handleMenuChange = function handleMenuChange2(_ref3) {
    var id2 = _ref3.id, props = _ref3.props;
    switch (id2) {
      case "duplicateandedit":
        props.duplicatePreset(activePresetForContextMenu);
        if (selectedTabIndex !== RNA_TAB_INDEX) {
          dispatch2(setSelectedTabIndex2(RNA_TAB_INDEX));
        }
        break;
      case "edit":
        props.editPreset(activePresetForContextMenu);
        if (selectedTabIndex !== RNA_TAB_INDEX) {
          dispatch2(setSelectedTabIndex2(RNA_TAB_INDEX));
        }
        break;
      case "deletepreset":
        dispatch2(openModal2("delete"));
        break;
    }
  };
  var ketcherEditorRootElement = document.querySelector(KETCHER_MACROMOLECULES_ROOT_NODE_SELECTOR);
  return ketcherEditorRootElement && !isSequenceEditInRNABuilderMode ? reactDomExports.createPortal(jsx(ContextMenu, {
    id: CONTEXT_MENU_ID.FOR_RNA,
    menuItems: RNAMenus,
    handleMenuChange
  }), ketcherEditorRootElement) : null;
};
var RnaPresetGroup = function RnaPresetGroup2(_ref3) {
  var presets = _ref3.presets, duplicatePreset = _ref3.duplicatePreset, editPreset = _ref3.editPreset;
  var activePreset = useAppSelector(selectActivePreset);
  var editor = useAppSelector(selectEditor);
  var _useContextMenu = Fe({
    id: CONTEXT_MENU_ID.FOR_RNA
  }), show = _useContextMenu.show;
  var dispatch2 = useDispatch();
  var resolvePhosphatePosition = function resolvePhosphatePosition2(preset) {
    var _preset$phosphatePosi;
    return (_preset$phosphatePosi = preset.phosphatePosition) !== null && _preset$phosphatePosi !== void 0 ? _preset$phosphatePosi : getRnaPresetPhosphatePosition(preset);
  };
  var validatePreset = function validatePreset2(preset) {
    var _preset$base, _preset$sugar, _preset$phosphate;
    var isBaseValid = true;
    var isSugarValid = true;
    var isPhosphateValid = true;
    if (preset !== null && preset !== void 0 && (_preset$base = preset.base) !== null && _preset$base !== void 0 && (_preset$base = _preset$base.props) !== null && _preset$base !== void 0 && _preset$base.MonomerCaps) {
      isBaseValid = "R1" in preset.base.props.MonomerCaps;
    }
    if (preset !== null && preset !== void 0 && (_preset$sugar = preset.sugar) !== null && _preset$sugar !== void 0 && (_preset$sugar = _preset$sugar.props) !== null && _preset$sugar !== void 0 && _preset$sugar.MonomerCaps) {
      var _preset$base2;
      if (isBaseValid && preset !== null && preset !== void 0 && (_preset$base2 = preset.base) !== null && _preset$base2 !== void 0 && (_preset$base2 = _preset$base2.props) !== null && _preset$base2 !== void 0 && _preset$base2.MonomerCaps) {
        isSugarValid = "R3" in preset.sugar.props.MonomerCaps;
      }
    }
    if (preset !== null && preset !== void 0 && (_preset$phosphate = preset.phosphate) !== null && _preset$phosphate !== void 0 && (_preset$phosphate = _preset$phosphate.props) !== null && _preset$phosphate !== void 0 && _preset$phosphate.MonomerCaps) {
      var _preset$sugar2;
      isPhosphateValid = "R1" in preset.phosphate.props.MonomerCaps;
      if (isSugarValid && preset !== null && preset !== void 0 && (_preset$sugar2 = preset.sugar) !== null && _preset$sugar2 !== void 0 && (_preset$sugar2 = _preset$sugar2.props) !== null && _preset$sugar2 !== void 0 && _preset$sugar2.MonomerCaps) {
        isSugarValid = "R2" in preset.sugar.props.MonomerCaps;
      }
    }
    return isBaseValid && isSugarValid && isPhosphateValid;
  };
  var selectPreset = function selectPreset2(preset) {
    return function() {
      var isPresetValid = validatePreset(preset);
      if (!isPresetValid && preset.name) {
        dispatch2(setInvalidPresetError2(preset.name));
        return;
      }
      dispatch2(setActivePreset2(preset));
      editor === null || editor === void 0 || editor.events.selectPreset.dispatch(preset);
      if (preset.name === activePreset.name) return;
      dispatch2(setIsEditMode2(false));
    };
  };
  var getMenuPosition = function getMenuPosition2(currentPresetCard) {
    var _currentPresetCard$of;
    var isDivCard = currentPresetCard instanceof HTMLDivElement;
    if (!isDivCard && currentPresetCard.parentElement) {
      currentPresetCard = currentPresetCard.parentElement;
    }
    var boundingBox = currentPresetCard.getBoundingClientRect();
    var parentBox = (_currentPresetCard$of = currentPresetCard.offsetParent) === null || _currentPresetCard$of === void 0 ? void 0 : _currentPresetCard$of.getBoundingClientRect();
    var contextMenuWidth = 140;
    var x2 = boundingBox.right - contextMenuWidth;
    var y2 = boundingBox.y + boundingBox.height / 2;
    if (parentBox !== null && parentBox !== void 0 && parentBox.x && (parentBox === null || parentBox === void 0 ? void 0 : parentBox.x) > x2) {
      x2 = boundingBox.x;
    }
    return {
      x: x2,
      y: y2
    };
  };
  var preview2 = useAppSelector(selectShowPreview);
  var dispatchShowPreview = reactExports.useCallback(function(payload) {
    return dispatch2(showPreview2(payload));
  }, [dispatch2]);
  var debouncedShowPreview = reactExports.useCallback(lodashExports.debounce(function(p) {
    return dispatchShowPreview(p);
  }, 500), [dispatchShowPreview]);
  var handleItemMouseLeave = function handleItemMouseLeave2() {
    debouncedShowPreview.cancel();
    dispatch2(showPreview2(void 0));
  };
  var handleItemMouseMove = function handleItemMouseMove2(preset, e) {
    handleItemMouseLeave();
    if (needSkipPreviewForElement(e.target)) {
      return;
    }
    if (preview2.type === PreviewType.Preset || !e.currentTarget) {
      return;
    }
    var monomers = [preset.sugar, preset.base, preset.phosphate];
    var cardCoordinates = e.currentTarget.getBoundingClientRect();
    var style = {
      left: "".concat(cardCoordinates.left + cardCoordinates.width, "px"),
      top: isAmbiguousMonomerLibraryItem(preset.base) ? calculateAmbiguousMonomerPreviewTop(preset.base)(cardCoordinates) : calculateNucleoElementPreviewTop(cardCoordinates),
      transform: "translate(-100%, 0)"
    };
    var previewData = isAmbiguousMonomerLibraryItem(preset.base) ? {
      type: PreviewType.AmbiguousMonomer,
      monomer: preset.base,
      presetMonomers: monomers,
      style
    } : {
      type: PreviewType.Preset,
      monomers,
      name: preset.name,
      idtAliases: preset.idtAliases,
      aliasAxoLabs: preset.aliasAxoLabs,
      phosphatePosition: resolvePhosphatePosition(preset),
      position: PresetPosition.Library,
      style
    };
    debouncedShowPreview(previewData);
  };
  var handleContextMenu = function handleContextMenu2(preset) {
    return function(event) {
      event.stopPropagation();
      dispatch2(setActivePresetForContextMenu2(preset));
      show({
        event,
        props: {
          duplicatePreset,
          editPreset
        },
        position: getMenuPosition(event.currentTarget)
      });
    };
  };
  return jsxs(GroupContainerColumn, {
    "data-testid": "rna-preset-group",
    children: [jsx(ItemsContainer, {
      children: presets.map(function(preset, index) {
        return jsx(RnaPresetItem$1, {
          isSelected: (activePreset === null || activePreset === void 0 ? void 0 : activePreset.name) === preset.name,
          preset,
          onClick: selectPreset(preset),
          onContextMenu: handleContextMenu(preset),
          onMouseMove: function onMouseMove(e) {
            return handleItemMouseMove(preset, e);
          },
          onMouseLeave: handleItemMouseLeave
        }, "".concat(preset.name).concat(index));
      })
    }), jsx(RNAContextMenu, {})]
  });
};
var MonomerList = function MonomerList2(_ref3) {
  var onItemClick = _ref3.onItemClick, libraryName = _ref3.libraryName, duplicatePreset = _ref3.duplicatePreset, editPreset = _ref3.editPreset;
  var monomers = useAppSelector(selectFilteredMonomers);
  var presets = useAppSelector(selectFilteredPresets);
  var activeTool = useAppSelector(selectEditorActiveTool);
  var isFavoriteTab = libraryName === MONOMER_LIBRARY_FAVORITES;
  var items = !isFavoriteTab ? selectMonomersInCategory(monomers, libraryName) : {
    monomers: selectMonomersInFavorites(monomers),
    presets: selectPresetsInFavorites(presets)
  };
  var monomerGroups = selectMonomerGroups(isFavoriteTab ? items.monomers : items);
  var ambiguousMonomers = isFavoriteTab ? selectAmbiguousMonomersInFavorites(monomers) : selectAmbiguousMonomersInCategory(monomers, MonomerGroups.PEPTIDES);
  var _useState = reactExports.useState(""), _useState2 = _slicedToArray(_useState, 2), selectedMonomers = _useState2[0], setSelectedMonomers = _useState2[1];
  reactExports.useEffect(function() {
    if (activeTool !== "monomer") {
      setSelectedMonomers("");
    }
  }, [activeTool]);
  return jsxs(MonomerListContainer, {
    children: [isFavoriteTab && monomerGroups.length > 0 && jsx("div", {
      children: "Monomers"
    }), monomerGroups.map(function(_ref22, _index, groups) {
      var groupItems = _ref22.groupItems, groupTitle = _ref22.groupTitle;
      return jsx(MonomerGroup, {
        title: groups.length === 1 ? void 0 : groupTitle,
        items: groupItems,
        libraryName,
        onItemClick,
        selectedMonomerUniqueKey: selectedMonomers
      }, groupTitle);
    }), isFavoriteTab && items.presets.length > 0 && jsxs(Fragment, {
      children: [jsx("div", {
        children: "Presets"
      }), jsx(RnaPresetGroup, {
        duplicatePreset,
        editPreset,
        presets: items.presets
      })]
    }), jsx(Fragment, {
      children: (libraryName === MONOMER_LIBRARY_PEPTIDES || isFavoriteTab) && ambiguousMonomers.map(function(group) {
        return jsx(MonomerGroup, {
          title: group.groupTitle,
          items: group.groupItems,
          libraryName,
          onItemClick,
          selectedMonomerUniqueKey: selectedMonomers
        }, group.groupTitle);
      })
    })]
  });
};
var RnaEditorCollapsedContainer = createStyled("div", {
  target: "e1fsx6x2"
} )({
  name: "kxxltl",
  styles: "display:flex;flex-direction:row;justify-content:space-between;align-items:center;padding:8px;background-color:#f7f9fa;border-radius:0 0 4px 4px"
} );
var MonomerName$3 = createStyled("span", {
  target: "e1fsx6x1"
} )("font-size:", function(props) {
  return props.theme.ketcher.font.size.medium;
}, ";overflow:hidden;text-overflow:ellipsis;color:", function(props) {
  return props.theme.ketcher.color.text.primary;
}, ";" + ("" ));
var TextContainer$1 = createStyled("div", {
  target: "e1fsx6x0"
} )({
  name: "1x17g94",
  styles: "display:flex;align-items:center;width:100%"
} );
var RnaEditorCollapsed = function RnaEditorCollapsed2(_ref3) {
  var name = _ref3.name, fullName = _ref3.fullName;
  var displayName = name !== null && name !== void 0 ? name : fullName;
  if (!displayName) {
    return null;
  }
  var title = fullName !== null && fullName !== void 0 ? fullName : displayName;
  return jsx(RnaEditorCollapsedContainer, {
    title,
    children: jsx(TextContainer$1, {
      children: jsx(MonomerName$3, {
        title,
        "aria-label": title,
        children: displayName
      })
    })
  });
};
var RnaEditorCollapsed$1 = reactExports.memo(RnaEditorCollapsed);
var GroupBlockContainer = createStyled("div", {
  target: "e1ie5fzr8"
} )(function(props) {
  var selected = props.selected, isEditMode = props.isEditMode, theme = props.theme;
  var backgroundColor = "transparent";
  if (selected) {
    backgroundColor = theme.ketcher.color.button.primary.active;
  } else if (isEditMode) {
    backgroundColor = theme.ketcher.color.background.primary;
  }
  return {
    height: "40px",
    position: "relative",
    marginLeft: isEditMode ? "30px" : "28.5px",
    display: "flex",
    alignItems: "center",
    border: isEditMode ? "none" : "1.5px solid ".concat(theme.ketcher.outline.color),
    backgroundColor,
    borderRadius: theme.ketcher.border.radius.regular,
    boxShadow: isEditMode ? theme.ketcher.shadow.regular : "none",
    padding: "5px 10px",
    color: selected ? "white" : "black",
    gap: "8px",
    cursor: "pointer",
    outlineOffset: "1px",
    boxSizing: "border-box",
    ":hover": {
      outline: theme.ketcher.outline.small
    },
    ":not(:last-child)": {
      ":after": {
        content: '""',
        position: "absolute",
        right: "100%",
        bottom: "calc(50% - 1px)",
        borderLeft: theme.ketcher.outline.medium,
        borderBottom: theme.ketcher.outline.medium,
        height: "2px",
        width: "17px"
      }
    },
    ":last-child": {
      ":after": {
        content: '""',
        position: "absolute",
        right: "100%",
        bottom: "calc(50% - 1px)",
        borderLeft: theme.ketcher.outline.medium,
        borderBottom: theme.ketcher.outline.medium,
        borderRadius: "0 0 0 4px",
        height: "130px",
        width: "17px"
      }
    }
  };
}, "" );
var TextContainer = createStyled("div", {
  target: "e1ie5fzr7"
} )({
  name: "1fttcpj",
  styles: "display:flex;flex-direction:column"
} );
var GroupName = createStyled("span", {
  target: "e1ie5fzr6"
} )("font-size:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.font.size.small;
}, ";color:", function(_ref22) {
  var selected = _ref22.selected, theme = _ref22.theme;
  return selected ? theme.ketcher.color.background.primary : theme.ketcher.color.text.light;
}, ";opacity:", function(_ref3) {
  var selected = _ref3.selected;
  return selected ? 0.4 : 1;
}, ";" + ("" ));
var MonomerName$2 = createStyled("span", {
  target: "e1ie5fzr5"
} )("margin-top:1px;font-size:", function(_ref4) {
  var theme = _ref4.theme;
  return theme.ketcher.font.size.medium;
}, ";color:", function(_ref5) {
  var selected = _ref5.selected, empty2 = _ref5.empty, theme = _ref5.theme;
  if (selected) {
    return theme.ketcher.color.button.text.primary;
  }
  if (empty2) {
    return "#b4b9d6";
  }
  return theme.ketcher.color.text.primary;
}, ";opacity:", function(_ref6) {
  var selected = _ref6.selected, empty2 = _ref6.empty;
  return selected && empty2 ? 0.4 : 1;
}, ";" + ("" ));
var GroupIconContainer = createStyled("div", {
  target: "e1ie5fzr4"
} )({
  name: "wgokoh",
  styles: "position:relative;width:16px;height:16px;display:flex;align-items:center;justify-content:center"
} );
var GroupIcon$2 = createStyled(Icon, {
  target: "e1ie5fzr3"
} )("fill:", function(_ref7) {
  var selected = _ref7.selected, empty2 = _ref7.empty, theme = _ref7.theme;
  if (empty2) {
    return "none";
  }
  if (selected) {
    return theme.ketcher.color.background.primary;
  }
  return theme.ketcher.color.icon.grey;
}, ";color:", function(_ref8) {
  var selected = _ref8.selected, theme = _ref8.theme;
  return selected ? theme.ketcher.color.background.primary : theme.ketcher.color.icon.grey;
}, ";" + ("" ));
var CompactGroupBlockContainer = createStyled("div", {
  target: "e1ie5fzr2"
} )("position:relative;width:60px;display:flex;flex-direction:column;gap:8px;padding:4px;border-radius:4px;box-shadow:0 1px 2px 0 rgba(180, 185, 214, 0.6);cursor:pointer;background-color:", function(_ref9) {
  var selected = _ref9.selected, theme = _ref9.theme;
  return selected ? theme.ketcher.color.button.primary.active : theme.ketcher.color.background.primary;
}, ";&:hover{outline:", function(_ref0) {
  var theme = _ref0.theme;
  return theme.ketcher.outline.selected.small;
}, ";}" + ("" ));
var CompactGroupConnection = createStyled("div", {
  target: "e1ie5fzr1"
} )("position:absolute;top:-35%;left:50%;height:15px;width:2px;background-color:", function(_ref1) {
  var theme = _ref1.theme;
  return theme.ketcher.outline.color;
}, ";" + ("" ));
var CompactGroupText = createStyled("p", {
  target: "e1ie5fzr0"
} )("margin:0;font-size:", function(_ref10) {
  var theme = _ref10.theme;
  return theme.ketcher.font.size.small;
}, ";font-weight:", function(_ref11) {
  var theme = _ref11.theme;
  return theme.ketcher.font.weight.regular;
}, ";color:", function(_ref12) {
  var selected = _ref12.selected, empty2 = _ref12.empty, theme = _ref12.theme;
  if (selected) {
    return theme.ketcher.color.button.text.primary;
  }
  if (empty2) {
    return "#b4b9d6";
  }
  return theme.ketcher.color.text.primary;
}, ";opacity:", function(_ref13) {
  var selected = _ref13.selected, empty2 = _ref13.empty;
  return selected && empty2 ? 0.4 : 1;
}, ";" + ("" ));
var groupNameToRnaEditorItemLabel = _defineProperty$1(_defineProperty$1(_defineProperty$1({}, MonomerGroups.SUGARS, "Sugar"), MonomerGroups.BASES, "Base"), MonomerGroups.PHOSPHATES, "Phosphate");
var GroupIcon = function GroupIcon2(_ref3) {
  var selected = _ref3.selected, empty2 = _ref3.empty, name = _ref3.name;
  return jsx(GroupIconContainer, {
    children: jsx(GroupIcon$2, {
      selected,
      empty: empty2,
      name
    })
  });
};
var GroupIcon$1 = reactExports.memo(GroupIcon);
var GroupBlockCompact = function GroupBlockCompact2(_ref3) {
  var groupName = _ref3.groupName, iconName = _ref3.iconName, monomerName = _ref3.monomerName, selected = _ref3.selected, onClick = _ref3.onClick, testid = _ref3.testid, children2 = _ref3.children;
  var isEditMode = useAppSelector(selectIsEditMode);
  var empty2 = !monomerName;
  return jsx(CompactGroupBlockContainer, {
    selected,
    onClick,
    isEditMode,
    "data-testid": testid,
    children: jsxs(Fragment, {
      children: [jsx(CompactGroupConnection, {}), jsx(GroupIcon$1, {
        name: iconName,
        selected,
        empty: empty2
      }), jsx(CompactGroupText, {
        selected,
        empty: empty2,
        children: monomerName !== null && monomerName !== void 0 ? monomerName : groupNameToRnaEditorItemLabel[groupName]
      }), children2]
    })
  });
};
var GroupBlockWide = function GroupBlockWide2(_ref3) {
  var groupName = _ref3.groupName, iconName = _ref3.iconName, monomerName = _ref3.monomerName, selected = _ref3.selected, onClick = _ref3.onClick, testid = _ref3.testid, children2 = _ref3.children;
  var isEditMode = useAppSelector(selectIsEditMode);
  var empty2 = !monomerName;
  return jsx(GroupBlockContainer, {
    selected,
    onClick,
    isEditMode,
    "data-testid": testid,
    children: jsxs(Fragment, {
      children: [jsx(GroupIcon$1, {
        name: iconName,
        selected,
        empty: empty2
      }), jsxs(TextContainer, {
        children: [jsx(GroupName, {
          selected,
          children: groupNameToRnaEditorItemLabel[groupName]
        }), jsx(MonomerName$2, {
          empty: empty2,
          selected,
          children: monomerName !== null && monomerName !== void 0 ? monomerName : "Not selected"
        })]
      }), children2]
    })
  });
};
function ownKeys$k(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$k(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$k(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$k(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var GroupBlock = function GroupBlock2(props) {
  var isCompactView = useIsCompactView();
  return isCompactView ? jsx(GroupBlockCompact, _objectSpread$k(_objectSpread$k({}, props), {}, {
    children: props.children
  })) : jsx(GroupBlockWide, _objectSpread$k(_objectSpread$k({}, props), {}, {
    children: props.children
  }));
};
var RnaEditorExpandedContainer = createStyled("div", {
  target: "e18wzlbg12"
} )(function(props) {
  return {
    display: "flex",
    flexDirection: "column",
    padding: "10px",
    backgroundColor: "#F7F9FA",
    borderRadius: "0 0 4px 4px",
    "&.rna-editor-expanded--sequence-edit-mode": {
      padding: "8px",
      paddingTop: "10px",
      border: "2px ".concat(props.theme.ketcher.color.editMode.sequenceInRNABuilder, " solid"),
      borderTop: "none"
    }
  };
}, "" );
var CompactViewName = createStyled("input", {
  target: "e18wzlbg11"
} )("width:100%;padding:6px;border:none;border-radius:4px;box-shadow:0 1px 2px 0 rgba(180, 185, 214, 0.6);&:hover,&:focus{outline:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.outline.selected.small;
}, ";}" + ("" ));
var GroupsContainer = createStyled("div", {
  target: "e18wzlbg10"
} )("width:100%;display:flex;flex-direction:", function(_ref22) {
  var compact = _ref22.compact;
  return compact ? "row" : "column";
}, ";justify-content:", function(_ref3) {
  var compact = _ref3.compact;
  return compact ? "space-between" : "flex-start";
}, ";gap:8px;margin-top:16px;" + ("" ));
createStyled("div", {
  target: "e18wzlbg9"
} )({
  name: "6erkce",
  styles: "margin-top:12px;display:flex;align-items:center;justify-content:space-between;gap:8px"
} );
createStyled("span", {
  target: "e18wzlbg8"
} )(function(_ref4) {
  var theme = _ref4.theme;
  return {
    fontSize: theme.ketcher.font.size.small,
    color: theme.ketcher.color.text.light
  };
}, "" );
createStyled("div", {
  target: "e18wzlbg7"
} )({
  name: "1yydxi7",
  styles: "display:flex;align-items:center;gap:8px"
} );
createStyled("button", {
  target: "e18wzlbg6"
} )(function(_ref5) {
  var theme = _ref5.theme, selected = _ref5.selected;
  return {
    minWidth: "40px",
    padding: "4px 8px",
    borderRadius: theme.ketcher.border.radius.regular,
    border: selected ? theme.ketcher.outline.selected.small : theme.ketcher.outline.grey.small,
    color: selected ? theme.ketcher.color.button.text.primary : theme.ketcher.color.text.primary,
    backgroundColor: selected ? theme.ketcher.color.button.primary.active : theme.ketcher.color.background.primary,
    cursor: "pointer",
    ":disabled": {
      opacity: 0.5,
      cursor: "not-allowed"
    }
  };
}, "" );
var ButtonsContainer = createStyled("div", {
  target: "e18wzlbg5"
} )({
  name: "zmhcg5",
  styles: "margin-top:16px;display:flex;justify-content:space-evenly;align-items:center;gap:8px"
} );
var StyledButton$3 = createStyled(Button, {
  target: "e18wzlbg4"
} )(function(props) {
  return {
    width: "100%",
    whiteSpace: "nowrap",
    fontSize: props.theme.ketcher.font.size.regular,
    backgroundColor: props.primary ? props.theme.ketcher.color.button.primary.active : void 0,
    color: props.primary && !props.disabled ? props.theme.ketcher.color.button.text.primary : props.theme.ketcher.color.text.light,
    outline: props.primary && !props.disabled ? props.theme.ketcher.outline.selected.small : props.theme.ketcher.outline.grey.small
  };
}, "" );
var NameContainer = createStyled("div", {
  target: "e18wzlbg3"
} )(function(props) {
  return {
    position: "relative",
    borderRadius: props.theme.ketcher.border.radius.regular,
    backgroundColor: props.theme.ketcher.color.background.primary,
    boxShadow: props.theme.ketcher.shadow.regular,
    cursor: "pointer",
    overflow: "hidden",
    padding: "0 6px 6px 6px",
    display: "flex",
    alignItems: "flex-end",
    height: "48px",
    outline: props.selected ? props.theme.ketcher.outline.selected.medium : "none",
    ":hover": {
      outline: props.selected ? void 0 : props.theme.ketcher.outline.small
    }
  };
}, "" );
var NameLine = createStyled("span", {
  target: "e18wzlbg2"
} )(function(props) {
  return {
    position: "absolute",
    top: "0",
    left: "0",
    width: "100%",
    height: "8px",
    backgroundColor: props.selected ? props.theme.ketcher.outline.selected.color : props.theme.ketcher.outline.color
  };
}, "" );
var NameInput = createStyled(Input$2, {
  target: "e18wzlbg1"
} )({
  name: "1jdipvd",
  styles: "width:100%;&:disabled{background:none;outline:none;color:inherit;}"
} );
var PresetName$1 = createStyled("div", {
  target: "e18wzlbg0"
} )({
  name: "1gz2b5f",
  styles: "overflow:hidden;text-overflow:ellipsis"
} );
var scrollToElement = function scrollToElement2(selector2) {
  var element = document.body.querySelector(selector2);
  element === null || element === void 0 || element.scrollIntoView();
};
var scrollToSelectedPreset = function scrollToSelectedPreset2(presetName) {
  scrollToElement('[data-rna-preset-item-name="'.concat(presetName, '"]'));
};
var scrollToSelectedMonomer = function scrollToSelectedMonomer2(monomerId) {
  scrollToElement('[data-monomer-item-id="'.concat(monomerId, '"]'));
};
function _createForOfIteratorHelper$4(r, e) {
  var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"];
  if (!t) {
    if (Array.isArray(r) || (t = _unsupportedIterableToArray$4(r)) || e) {
      t && (r = t);
      var _n = 0, F = function F2() {
      };
      return { s: F, n: function n() {
        return _n >= r.length ? { done: true } : { done: false, value: r[_n++] };
      }, e: function e3(r2) {
        throw r2;
      }, f: F };
    }
    throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.");
  }
  var o, a = true, u = false;
  return { s: function s() {
    t = t.call(r);
  }, n: function n() {
    var r2 = t.next();
    return a = r2.done, r2;
  }, e: function e3(r2) {
    u = true, o = r2;
  }, f: function f() {
    try {
      a || null == t["return"] || t["return"]();
    } finally {
      if (u) throw o;
    }
  } };
}
function _unsupportedIterableToArray$4(r, a) {
  if (r) {
    if ("string" == typeof r) return _arrayLikeToArray$4(r, a);
    var t = {}.toString.call(r).slice(8, -1);
    return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray$4(r, a) : void 0;
  }
}
function _arrayLikeToArray$4(r, a) {
  (null == a || a > r.length) && (a = r.length);
  for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e];
  return n;
}
var getNucleotideMonomerGroupName = function getNucleotideMonomerGroupName2(nameSet) {
  if (nameSet.size === 0) return "";
  return nameSet.size === 1 ? _toConsumableArray(nameSet)[0] : "[multiple]";
};
var generateSequenceSelectionGroupNames = function generateSequenceSelectionGroupNames2(labeledNucleotides) {
  if (!(labeledNucleotides !== null && labeledNucleotides !== void 0 && labeledNucleotides.length)) return;
  var namesSets = {
    sugarLabel: /* @__PURE__ */ new Set(),
    baseLabel: /* @__PURE__ */ new Set(),
    phosphateLabel: /* @__PURE__ */ new Set()
  };
  var _iterator = _createForOfIteratorHelper$4(labeledNucleotides), _step;
  try {
    for (_iterator.s(); !(_step = _iterator.n()).done; ) {
      var labeledNucleotide = _step.value;
      for (var _i = 0, _arr = ["sugarLabel", "baseLabel", "phosphateLabel"]; _i < _arr.length; _i++) {
        var item = _arr[_i];
        if (labeledNucleotide !== null && labeledNucleotide !== void 0 && labeledNucleotide[item] || !(labeledNucleotide !== null && labeledNucleotide !== void 0 && labeledNucleotide[item]) && labeledNucleotide.type === Entities.Nucleoside && !labeledNucleotide.isNucleosideConnectedAndSelectedWithPhosphate) namesSets[item].add(labeledNucleotide === null || labeledNucleotide === void 0 ? void 0 : labeledNucleotide[item]);
      }
    }
  } catch (err) {
    _iterator.e(err);
  } finally {
    _iterator.f();
  }
  return {
    Sugars: getNucleotideMonomerGroupName(namesSets.sugarLabel),
    Bases: getNucleotideMonomerGroupName(namesSets.baseLabel),
    Phosphates: getNucleotideMonomerGroupName(namesSets.phosphateLabel)
  };
};
var generateSequenceSelectionName = function generateSequenceSelectionName2(labeledNucleoelements) {
  var _groupNames$Phosphate;
  var groupNames = generateSequenceSelectionGroupNames(labeledNucleoelements);
  return "".concat(groupNames === null || groupNames === void 0 ? void 0 : groupNames.Sugars, "(").concat(groupNames === null || groupNames === void 0 ? void 0 : groupNames.Bases, ")").concat((_groupNames$Phosphate = groupNames === null || groupNames === void 0 ? void 0 : groupNames.Phosphates) !== null && _groupNames$Phosphate !== void 0 ? _groupNames$Phosphate : "");
};
var resetRnaBuilderCommon = function resetRnaBuilderCommon2(dispatch2) {
  dispatch2(setActivePresetMonomerGroup2(null));
  dispatch2(setIsEditMode2(false));
};
var resetRnaBuilder = function resetRnaBuilder2(dispatch2) {
  resetRnaBuilderCommon(dispatch2);
};
var resetRnaBuilderAfterSequenceUpdate = function resetRnaBuilderAfterSequenceUpdate2(dispatch2, editor) {
  var _editor$mode;
  resetRnaBuilderCommon(dispatch2);
  dispatch2(setSequenceSelection2([]));
  editor === null || editor === void 0 || editor.events.turnOffSequenceEditInRNABuilderMode.dispatch();
  if ((editor === null || editor === void 0 || (_editor$mode = editor.mode) === null || _editor$mode === void 0 ? void 0 : _editor$mode.modeName) === "sequence-layout-mode") editor.mode.turnOffEditMode();
};
var getCountOfNucleoelements = function getCountOfNucleoelements2(selections) {
  return selections.filter(function(selection2) {
    if (selection2.type) {
      return selection2.type === Entities.Nucleotide || selection2.type === Entities.Nucleoside;
    } else if (selection2.node) {
      return selection2.node instanceof Nucleotide || selection2.node instanceof Nucleoside;
    }
    return false;
  }).length;
};
var styles$3 = { "phosphatePositionIconWrapper": "RnaEditorExpanded-module_phosphatePositionIconWrapper__XHea5", "active": "RnaEditorExpanded-module_active__9PKEX", "hover": "RnaEditorExpanded-module_hover__0ZbV5", "phosphatePositionIconWrapperOnPresetCard": "RnaEditorExpanded-module_phosphatePositionIconWrapperOnPresetCard__-IbfN", "phosphatePositionIconWrapperOnPresetCardActive": "RnaEditorExpanded-module_phosphatePositionIconWrapperOnPresetCardActive__bAVbU", "phosphatePositionSelector": "RnaEditorExpanded-module_phosphatePositionSelector__NE5RX", "phosphatePositionTrigger": "RnaEditorExpanded-module_phosphatePositionTrigger__IpdSG", "phosphatePositionOption": "RnaEditorExpanded-module_phosphatePositionOption__GO-S4", "phosphatePositionOptionDisabled": "RnaEditorExpanded-module_phosphatePositionOptionDisabled__oxZ6W" };
function ownKeys$j(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$j(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$j(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$j(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var RnaEditorExpanded = function RnaEditorExpanded2(_ref3) {
  var _activePreset$connect;
  var isEditMode = _ref3.isEditMode, onDuplicate = _ref3.onDuplicate;
  var groupsData = [{
    groupName: MonomerGroups.SUGARS,
    iconName: "sugar",
    testId: "rna-builder-slot--sugar"
  }, {
    groupName: MonomerGroups.BASES,
    iconName: "base",
    testId: "rna-builder-slot--base"
  }, {
    groupName: MonomerGroups.PHOSPHATES,
    iconName: "phosphate",
    testId: "rna-builder-slot--phosphate"
  }];
  var dispatch2 = useDispatch();
  var isSequenceMode = useLayoutMode() === "sequence-layout-mode";
  var activePreset = useAppSelector(selectActivePreset);
  var isActivePresetEmpty = useAppSelector(selectIsActivePresetNewAndEmpty);
  var activeMonomerGroup = useAppSelector(selectActiveRnaBuilderItem);
  var editor = useAppSelector(selectEditor);
  var presets = useAppSelector(selectAllPresets);
  var activePresetMonomerGroup = useAppSelector(selectActivePresetMonomerGroup);
  var _useState = reactExports.useState(activePreset), _useState2 = _slicedToArray(_useState, 2), newPreset = _useState2[0], setNewPreset = _useState2[1];
  var _useState3 = reactExports.useState(activePreset !== null && activePreset !== void 0 && (_activePreset$connect = activePreset.connections) !== null && _activePreset$connect !== void 0 && _activePreset$connect.length ? getRnaPresetPhosphatePosition(activePreset) : void 0), _useState4 = _slicedToArray(_useState3, 2), selectedPhosphatePosition = _useState4[0], setSelectedPhosphatePosition = _useState4[1];
  var resolvePhosphatePosition = function resolvePhosphatePosition2(preset) {
    var _preset$connections;
    if (!(preset !== null && preset !== void 0 && preset.phosphate)) {
      return void 0;
    }
    var _getPhosphatePosition = getPhosphatePositionAvailability(preset), isRightPositionAvailable = _getPhosphatePosition.is3PrimeAvailable, isLeftPositionAvailable = _getPhosphatePosition.is5PrimeAvailable;
    if (selectedPhosphatePosition === "left" && isLeftPositionAvailable) {
      return "left";
    }
    if (selectedPhosphatePosition === "right" && isRightPositionAvailable) {
      return "right";
    }
    if ((_preset$connections = preset.connections) !== null && _preset$connections !== void 0 && _preset$connections.length) {
      var presetPhosphatePosition = getRnaPresetPhosphatePosition(preset);
      if (presetPhosphatePosition === "left" && isLeftPositionAvailable || presetPhosphatePosition === "right" && isRightPositionAvailable) {
        return presetPhosphatePosition;
      }
    }
    if (isSequenceMode && isRightPositionAvailable) {
      return "right";
    }
    if (isLeftPositionAvailable && !isRightPositionAvailable) {
      return "left";
    }
    if (isRightPositionAvailable && !isLeftPositionAvailable) {
      return "right";
    }
    return void 0;
  };
  var sequenceSelection = useAppSelector(selectSequenceSelection);
  var sequenceSelectionName = useAppSelector(selectSequenceSelectionName);
  var isSequenceEditInRNABuilderMode = useAppSelector(selectIsSequenceEditInRNABuilderMode);
  var _useState5 = reactExports.useState(false), _useState6 = _slicedToArray(_useState5, 2), isSequenceSelectionUpdated = _useState6[0], setIsSequenceSelectionUpdated = _useState6[1];
  var _useState7 = reactExports.useState(generateSequenceSelectionGroupNames(sequenceSelection)), _useState8 = _slicedToArray(_useState7, 2), sequenceSelectionGroupNames = _useState8[0], setSequenceSelectionGroupNames = _useState8[1];
  var phosphatePosition = resolvePhosphatePosition(newPreset);
  var _getPhosphatePosition2 = getPhosphatePositionAvailability(newPreset || {}), is3PrimeAvailable = _getPhosphatePosition2.is3PrimeAvailable, is5PrimeAvailable = _getPhosphatePosition2.is5PrimeAvailable;
  var isPhosphateOrientationRequired = Boolean(newPreset === null || newPreset === void 0 ? void 0 : newPreset.phosphate) && is3PrimeAvailable && is5PrimeAvailable;
  var saveButtonDisabledByPhosphatePosition = !phosphatePosition && isPhosphateOrientationRequired;
  var saveButtonDisabledTooltip = saveButtonDisabledByPhosphatePosition ? "Before saving you must choose the position of the phosphate." : "";
  var phosphatePositionDisabledTooltip = {
    left: "Sugar must have R1, and phosphate must have R2.",
    right: "Sugar must have R2, and phosphate must have R1."
  };
  var updatePresetMonomerGroup = function updatePresetMonomerGroup2() {
    if (activePresetMonomerGroup) {
      var groupName = monomerGroupToPresetGroup[activePresetMonomerGroup.groupName];
      var currentPreset = _objectSpread$j(_objectSpread$j({}, newPreset), {}, _defineProperty$1({}, groupName, activePresetMonomerGroup.groupItem));
      setNewPreset(currentPreset);
      return currentPreset;
    }
    return newPreset;
  };
  reactExports.useEffect(function() {
    var _activePreset$connect2;
    setNewPreset(activePreset);
    setSelectedPhosphatePosition(activePreset !== null && activePreset !== void 0 && (_activePreset$connect2 = activePreset.connections) !== null && _activePreset$connect2 !== void 0 && _activePreset$connect2.length ? getRnaPresetPhosphatePosition(activePreset) : void 0);
  }, [activePreset]);
  reactExports.useEffect(function() {
    if (!sequenceSelection) return;
    if (getCountOfNucleoelements(sequenceSelection) === 1) {
      dispatch2(setSequenceSelectionName2(generateSequenceSelectionName(sequenceSelection)));
    }
    setSequenceSelectionGroupNames(generateSequenceSelectionGroupNames(sequenceSelection));
  }, [dispatch2, sequenceSelection]);
  reactExports.useEffect(function() {
    if (activeMonomerGroup !== RnaBuilderPresetsItem.Presets && isEditMode) {
      if (isSequenceEditInRNABuilderMode && activePresetMonomerGroup) {
        var monomerType = monomerGroupToPresetGroup[activePresetMonomerGroup.groupName];
        var field = "".concat(monomerType, "Label");
        var updatedSequenceSelection = sequenceSelection.map(function(node) {
          if (node.isNucleosideConnectedAndSelectedWithPhosphate && field === "phosphateLabel" || node.type === Entities.Phosphate && (field === "sugarLabel" || field === "baseLabel")) {
            return node;
          }
          return _objectSpread$j(_objectSpread$j({}, node), {}, _defineProperty$1(_defineProperty$1({}, field, activePresetMonomerGroup.groupItem.label), "rnaBaseMonomerItem", activePresetMonomerGroup.groupName === "Bases" ? activePresetMonomerGroup.groupItem : node.rnaBaseMonomerItem));
        });
        setIsSequenceSelectionUpdated(true);
        dispatch2(setSequenceSelection2(updatedSequenceSelection));
      } else {
        var currentPreset = updatePresetMonomerGroup();
        var resolvedPhosphatePosition = resolvePhosphatePosition(currentPreset);
        var presetFullName = newPreset === null || newPreset === void 0 ? void 0 : newPreset.name;
        if (!currentPreset.editedName) {
          presetFullName = selectPresetFullName(_objectSpread$j(_objectSpread$j({}, currentPreset), {}, {
            connections: buildRnaPresetConnections(currentPreset, resolvedPhosphatePosition)
          }));
        }
        setNewPreset(_objectSpread$j(_objectSpread$j({}, currentPreset), {}, {
          name: presetFullName
        }));
      }
    }
  }, [activePresetMonomerGroup === null || activePresetMonomerGroup === void 0 ? void 0 : activePresetMonomerGroup.groupItem, isSequenceEditInRNABuilderMode, selectedPhosphatePosition]);
  var scrollToActiveItemInLibrary = function scrollToActiveItemInLibrary2(selectedGroup, selectedMonomer) {
    if (selectedGroup === RnaBuilderPresetsItem.Presets) {
      scrollToSelectedPreset(newPreset === null || newPreset === void 0 ? void 0 : newPreset.name);
      if (newPreset) {
        editor === null || editor === void 0 || editor.events.selectPreset.dispatch(newPreset);
      }
      return;
    }
    var activeMonomerInSelectedGroup = newPreset[monomerGroupToPresetGroup[selectedGroup]];
    if (activeMonomerInSelectedGroup) {
      scrollToSelectedMonomer(getMonomerUniqueKey(activeMonomerInSelectedGroup));
    } else if (selectedMonomer) {
      scrollToSelectedMonomer(selectedMonomer);
    }
  };
  var selectGroup = function selectGroup2(selectedGroup) {
    return function() {
      var selectedRNAPartMonomer = selectCurrentMonomerGroup(newPreset, selectedGroup);
      if (selectedRNAPartMonomer && !isSequenceMode) {
        editor === null || editor === void 0 || editor.events.selectMonomer.dispatch(selectedRNAPartMonomer);
      }
      if (newPreset[monomerGroupToPresetGroup[selectedGroup]]) {
        dispatch2(setActiveMonomerKey2(getMonomerUniqueKey(newPreset[monomerGroupToPresetGroup[selectedGroup]])));
      }
      dispatch2(setActiveRnaBuilderItem2(selectedGroup));
      dispatch2(recalculateRnaBuilderValidations2({
        rnaPreset: newPreset,
        isEditMode,
        selectedPhosphatePosition
      }));
      var selectedMonomer = "";
      if (isSequenceEditInRNABuilderMode && sequenceSelection.length > 0) {
        var firstBaseLabel = sequenceSelection[0].baseLabel;
        var allBasesSame = firstBaseLabel && sequenceSelection.every(function(node) {
          return node.baseLabel === firstBaseLabel;
        });
        if (allBasesSame) {
          var baseMonomerItem = sequenceSelection[0].rnaBaseMonomerItem;
          if (baseMonomerItem) {
            selectedMonomer = getMonomerUniqueKey(baseMonomerItem);
            dispatch2(setActiveMonomerKey2(selectedMonomer));
          }
        }
      }
      setTimeout(function() {
        return scrollToActiveItemInLibrary(selectedGroup, selectedMonomer);
      }, 100);
    };
  };
  var onChangeName = function onChangeName2(event) {
    if (isEditMode) {
      var newPresetName = event.target.value;
      setNewPreset(_objectSpread$j(_objectSpread$j({}, newPreset), {}, {
        name: newPresetName.trim(),
        editedName: true
      }));
    }
  };
  var setPhosphatePosition = function setPhosphatePosition2(position) {
    setSelectedPhosphatePosition(position);
    dispatch2(recalculateRnaBuilderValidations2({
      rnaPreset: newPreset,
      isEditMode,
      selectedPhosphatePosition: position
    }));
  };
  var renderPhosphateTriggerIcon = function renderPhosphateTriggerIcon2(position) {
    var isActive = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : false;
    var highlightOnHover = arguments.length > 2 && arguments[2] !== void 0 ? arguments[2] : false;
    return jsx("div", {
      className: clsx$2(styles$3.phosphatePositionIconWrapper, isActive && styles$3.active, highlightOnHover && styles$3.hover),
      children: position === "left" ? jsx(Icon, {
        name: "preset-left-phosphate"
      }) : jsx(Icon, {
        name: "preset-right-phosphate"
      })
    });
  };
  var getPhosphatePositionTooltip = function getPhosphatePositionTooltip2(position) {
    return position === "left" ? "Phosphate on the left" : "Phosphate on the right";
  };
  var renderPhosphatePositionOption = function renderPhosphatePositionOption2(position, isDisabled) {
    var tooltip;
    if (isDisabled) {
      tooltip = phosphatePositionDisabledTooltip[position];
    } else if (selectedPhosphatePosition === position) {
      tooltip = getPhosphatePositionTooltip(position);
    } else {
      tooltip = "Switch to ".concat(position);
    }
    return jsx(Tooltip, {
      title: tooltip,
      children: jsx("span", {
        children: jsx("button", {
          type: "button",
          className: clsx$2(styles$3.phosphatePositionOption, isDisabled && styles$3.phosphatePositionOptionDisabled),
          disabled: isDisabled,
          onClick: function onClick() {
            setPhosphatePosition(position);
          },
          children: renderPhosphateTriggerIcon(position, false, true)
        })
      })
    }, position);
  };
  var renderPhosphatePositionSelector = function renderPhosphatePositionSelector2(position) {
    var _ref22;
    var triggerDisabled = !is5PrimeAvailable && !is3PrimeAvailable;
    var triggerPosition = (_ref22 = position !== null && position !== void 0 ? position : selectedPhosphatePosition) !== null && _ref22 !== void 0 ? _ref22 : "right";
    var isPhosphateGroupActive = activeMonomerGroup === MonomerGroups.PHOSPHATES;
    var showPhosphatePositionTooltip = !isEditMode || !isPhosphateGroupActive;
    return jsxs("div", {
      className: clsx$2(styles$3.phosphatePositionIconWrapperOnPresetCard, isPhosphateGroupActive && !triggerDisabled && styles$3.phosphatePositionIconWrapperOnPresetCardActive),
      children: [jsx(Tooltip, {
        title: showPhosphatePositionTooltip ? getPhosphatePositionTooltip(triggerPosition) : "",
        children: jsx("span", {
          children: jsx("button", {
            type: "button",
            className: styles$3.phosphatePositionTrigger,
            disabled: triggerDisabled,
            "aria-label": "Select phosphate position",
            children: renderPhosphateTriggerIcon(triggerPosition, isPhosphateGroupActive)
          })
        })
      }), !triggerDisabled && !showPhosphatePositionTooltip ? jsxs("div", {
        className: styles$3.phosphatePositionSelector,
        children: [renderPhosphatePositionOption("left", !is5PrimeAvailable), renderPhosphatePositionOption("right", !is3PrimeAvailable)]
      }) : null]
    });
  };
  var onUpdateSequence = function onUpdateSequence2() {
    if (getCountOfNucleoelements(sequenceSelection) > 1) {
      dispatch2(openModal2("updateSequenceInRNABuilder"));
    } else {
      editor === null || editor === void 0 || editor.events.modifySequenceInRnaBuilder.dispatch(sequenceSelection);
      resetRnaBuilderAfterSequenceUpdate(dispatch2, editor);
    }
  };
  var onSave = function onSave2() {
    if (!(newPreset !== null && newPreset !== void 0 && newPreset.name)) {
      return;
    }
    var resolvedPhosphatePosition = resolvePhosphatePosition(newPreset);
    if (newPreset !== null && newPreset !== void 0 && newPreset.phosphate && !resolvedPhosphatePosition) {
      return;
    }
    var presetToSave = _objectSpread$j(_objectSpread$j({}, newPreset), {}, {
      connections: buildRnaPresetConnections(newPreset, resolvedPhosphatePosition)
    });
    var presetWithSameName = presets.find(function(preset) {
      return preset.name === presetToSave.name;
    });
    if (presetWithSameName && activePreset.nameInList !== presetWithSameName.name) {
      dispatch2(setUniqueNameError2(presetToSave.name));
      return;
    }
    dispatch2(savePreset2(presetToSave));
    dispatch2(setActivePreset2(presetToSave));
    if (!isSequenceMode) {
      editor === null || editor === void 0 || editor.events.selectPreset.dispatch(presetToSave);
    }
    setTimeout(function() {
      scrollToSelectedPreset(presetToSave.name);
    }, 0);
    resetRnaBuilder(dispatch2);
  };
  var onCancel = function onCancel2() {
    if (isSequenceEditInRNABuilderMode) {
      resetRnaBuilderAfterSequenceUpdate(dispatch2, editor);
    } else {
      var _activePreset$connect3;
      setNewPreset(activePreset);
      setSelectedPhosphatePosition(activePreset !== null && activePreset !== void 0 && (_activePreset$connect3 = activePreset.connections) !== null && _activePreset$connect3 !== void 0 && _activePreset$connect3.length ? getRnaPresetPhosphatePosition(activePreset) : void 0);
      resetRnaBuilder(dispatch2);
    }
  };
  var turnOnEditMode = function turnOnEditMode2() {
    dispatch2(setIsEditMode2(true));
  };
  var getMonomerName3 = function getMonomerName4(groupName) {
    var _selectCurrentMonomer, _selectCurrentMonomer2, _selectCurrentMonomer3;
    if (activePresetMonomerGroup && activePresetMonomerGroup.groupName === groupName) {
      return activePresetMonomerGroup.groupItem.label;
    }
    var result = (_selectCurrentMonomer = (_selectCurrentMonomer2 = selectCurrentMonomerGroup(newPreset, groupName)) === null || _selectCurrentMonomer2 === void 0 ? void 0 : _selectCurrentMonomer2.label) !== null && _selectCurrentMonomer !== void 0 ? _selectCurrentMonomer : (_selectCurrentMonomer3 = selectCurrentMonomerGroup(newPreset, groupName)) === null || _selectCurrentMonomer3 === void 0 ? void 0 : _selectCurrentMonomer3.props.MonomerName;
    return result || void 0;
  };
  var getMonomersName = function getMonomersName2(groupName) {
    if (!sequenceSelectionGroupNames) return "";
    return sequenceSelectionGroupNames[groupName];
  };
  reactExports.useEffect(function() {
    var handleKeyDown = function handleKeyDown2(event) {
      if (event.key === "Escape") {
        onCancel();
        event.preventDefault();
        event.stopPropagation();
      } else if (event.key === "Enter") {
        isSequenceEditInRNABuilderMode ? onUpdateSequence() : editor === null || editor === void 0 ? void 0 : editor.events.startNewSequence.dispatch({});
        event.preventDefault();
        event.stopPropagation();
      }
    };
    editor === null || editor === void 0 || editor.events.keyDown.add(handleKeyDown);
    return function() {
      editor === null || editor === void 0 || editor.events.keyDown.remove(handleKeyDown);
    };
  }, [editor, sequenceSelection]);
  var mainButton;
  var isSaveButtonDisabled = !selectIsPresetReadyToSave(newPreset) || saveButtonDisabledByPhosphatePosition;
  if (isActivePresetEmpty && !isSequenceEditInRNABuilderMode) {
    mainButton = jsx(Tooltip, {
      title: saveButtonDisabledTooltip,
      children: jsx(StyledButton$3, {
        disabled: isSaveButtonDisabled,
        primary: true,
        "data-testid": "add-to-presets-btn",
        onClick: onSave,
        children: "Add to Presets"
      })
    });
  } else if (isEditMode) {
    mainButton = jsx(Tooltip, {
      title: saveButtonDisabledTooltip,
      children: jsx(StyledButton$3, {
        primary: true,
        disabled: isSequenceEditInRNABuilderMode ? !isSequenceSelectionUpdated : isSaveButtonDisabled,
        "data-testid": "save-btn",
        onClick: isSequenceEditInRNABuilderMode ? onUpdateSequence : onSave,
        children: isSequenceEditInRNABuilderMode ? "Update" : "Save"
      })
    });
  } else {
    mainButton = jsx(StyledButton$3, {
      "data-testid": "edit-btn",
      onClick: turnOnEditMode,
      disabled: activePreset["default"],
      children: "Edit"
    });
  }
  var isCompactView = useIsCompactView();
  return jsxs(RnaEditorExpandedContainer, {
    "data-testid": "rna-editor-expanded",
    className: clsx$2(isSequenceEditInRNABuilderMode && "rna-editor-expanded--sequence-edit-mode"),
    children: [isCompactView ? jsx(CompactViewName, {
      value: isSequenceEditInRNABuilderMode ? sequenceSelectionName : newPreset === null || newPreset === void 0 ? void 0 : newPreset.name,
      placeholder: "Name your structure",
      "data-testid": "name-your-structure-editbox",
      disabled: isSequenceEditInRNABuilderMode,
      onChange: onChangeName
    }) : jsxs(NameContainer, {
      selected: activeMonomerGroup === RnaBuilderPresetsItem.Presets,
      onClick: function onClick() {
        return selectGroup(RnaBuilderPresetsItem.Presets);
      },
      children: [isEditMode ? jsx(NameInput, {
        value: isSequenceEditInRNABuilderMode ? sequenceSelectionName : newPreset === null || newPreset === void 0 ? void 0 : newPreset.name,
        placeholder: "Name your structure",
        "data-testid": "name-your-structure-editbox",
        disabled: isSequenceEditInRNABuilderMode,
        onChange: onChangeName
      }) : jsx(PresetName$1, {
        children: newPreset === null || newPreset === void 0 ? void 0 : newPreset.name
      }), jsx(NameLine, {
        selected: activeMonomerGroup === RnaBuilderPresetsItem.Presets
      })]
    }), jsx(GroupsContainer, {
      compact: isCompactView,
      children: groupsData.map(function(_ref32) {
        var groupName = _ref32.groupName, iconName = _ref32.iconName, testId = _ref32.testId;
        var isPhosphateGroup = groupName === MonomerGroups.PHOSPHATES;
        return jsx(GroupBlock, {
          selected: activeMonomerGroup === groupName,
          groupName,
          monomerName: isSequenceEditInRNABuilderMode ? getMonomersName(groupName) : getMonomerName3(groupName),
          iconName,
          testid: testId,
          onClick: selectGroup(groupName),
          children: isPhosphateGroup ? renderPhosphatePositionSelector(phosphatePosition) : null
        }, groupName);
      })
    }), jsxs(ButtonsContainer, {
      children: [isEditMode ? jsx(StyledButton$3, {
        "data-testid": "cancel-btn",
        onClick: onCancel,
        children: "Cancel"
      }) : jsx(StyledButton$3, {
        "data-testid": "duplicate-btn",
        disabled: !selectIsPresetReadyToSave(newPreset),
        onClick: function onClick() {
          return onDuplicate(newPreset);
        },
        children: "Duplicate and Edit"
      }), mainButton]
    })]
  });
};
var RnaEditorContainer = createStyled("div", {
  target: "e1ms1w5g2"
} )({
  name: "1tk8yx0",
  styles: "padding:8px"
} );
var StyledHeader = createStyled("button", {
  target: "e1ms1w5g1"
} )("width:100%;display:flex;justify-content:space-between;align-items:center;padding:8px;background-color:", function(props) {
  return props.theme.ketcher.color.background.primary;
}, ";font-weight:", function(props) {
  return props.theme.ketcher.font.weight.regular;
}, ";font-size:", function(props) {
  return props.theme.ketcher.font.size.regular;
}, ";border:none;border-radius:4px;text-transform:none;cursor:pointer;&.styled-header--sequence-edit-mode{background-color:", function(props) {
  return props.theme.ketcher.color.editMode.sequenceInRNABuilder;
}, ";}&.styled-header--expanded,&.styled-header--active-preset{border-radius:4px 4px 0 0;}" + ("" ));
var ExpandIcon = createStyled(Icon, {
  target: "e1ms1w5g0"
} )("height:16px;width:16px;transform:", function(props) {
  return props.expanded ? "rotate(180deg)" : "none";
}, ";" + ("" ));
var RnaEditor = function RnaEditor2(_ref3) {
  var duplicatePreset = _ref3.duplicatePreset;
  var activePreset = useAppSelector(selectActivePreset);
  var isEditMode = useAppSelector(selectIsEditMode);
  var isSequenceEditInRNABuilderMode = useAppSelector(selectIsSequenceEditInRNABuilderMode);
  var activePresetFullName = selectPresetFullName(activePreset);
  var dispatch2 = useAppDispatch();
  var _useState = reactExports.useState(false), _useState2 = _slicedToArray(_useState, 2), expanded = _useState2[0], setExpanded = _useState2[1];
  reactExports.useEffect(function() {
    if (activePreset) {
      if (activePreset.name || isEditMode) setExpanded(true);
      return;
    }
    dispatch2(createNewPreset2());
    dispatch2(setActiveRnaBuilderItem2(RnaBuilderPresetsItem.Presets));
  }, [activePreset]);
  reactExports.useEffect(function() {
    dispatch2(recalculateRnaBuilderValidations2({
      rnaPreset: activePreset,
      isEditMode
    }));
  }, [isEditMode]);
  var expandEditor = function expandEditor2() {
    setExpanded(!expanded);
    if (!(activePreset !== null && activePreset !== void 0 && activePreset.nameInList)) {
      dispatch2(setIsEditMode2(true));
    }
  };
  return jsxs(RnaEditorContainer, {
    "data-testid": "rna-editor",
    children: [jsxs(StyledHeader, {
      className: clsx$2(isSequenceEditInRNABuilderMode && "styled-header--sequence-edit-mode", expanded && "styled-header--expanded", (activePreset === null || activePreset === void 0 ? void 0 : activePreset.name) && "styled-header--active-preset"),
      onClick: expandEditor,
      "data-testid": "rna-builder-expand-button",
      children: ["RNA Builder", jsx(ExpandIcon, {
        expanded,
        name: "chevron"
      })]
    }), activePreset && (expanded ? jsx(RnaEditorExpanded, {
      isEditMode,
      onDuplicate: duplicatePreset
    }) : jsx(RnaEditorCollapsed$1, {
      name: activePreset.name,
      fullName: activePresetFullName
    }))]
  });
};
var RnaBuilderContainer = createStyled("div", {
  target: "e1ocltcl0"
} )({
  name: "16fpk5u",
  styles: "height:100%;width:100%;display:flex;flex-direction:column;justify-content:space-between"
} );
var scrollbarThin = function scrollbarThin2(_ref3) {
  var theme = _ref3.ketcher;
  return css("scrollbar-width:thin;scrollbar-color:", theme.color.scroll.regular, " ", theme.color.scroll.inactive, ";&::-webkit-scrollbar{width:4px;height:4px;background-color:", theme.color.scroll.inactive, ";border-radius:2px;-webkit-border-radius:2px;}&::-webkit-scrollbar-thumb{background-color:", theme.color.scroll.regular, ";border-radius:2px;-webkit-border-radius:2px;}&::-webkit-scrollbar-thumb:active{background-color:", theme.color.scroll.regular, ";}" + ("" ), "" );
};
var styles$2 = { "expandButton": "Modal-module_expandButton__J1QYl" };
function ownKeys$i(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$i(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$i(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$i(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var StyledDialog = createStyled(Dialog, {
  target: "e45wfhi5"
} )({
  name: "dzuq2w",
  styles: ".MuiPaper-root{min-width:304px;}"
} );
var Header$1 = createStyled(DialogTitle, {
  target: "e45wfhi4"
} )(function(_ref3) {
  var theme = _ref3.theme, hideborder = _ref3.hideborder;
  return {
    padding: "2px 4px 2px 12px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    fontFamily: "".concat(theme.ketcher.font.family.inter),
    fontSize: "".concat(theme.ketcher.font.size.medium),
    fontWeight: 500,
    textTransform: "capitalize",
    borderBottom: hideborder ? "none" : "1px solid rgba(202, 211, 221, 1)"
  };
}, "" );
var Title = createStyled("div", {
  target: "e45wfhi3"
} )({
  name: "10by1a4",
  styles: "margin-right:10px;font-size:14px"
} );
var StyledIcon$1 = createStyled(Icon, {
  target: "e45wfhi2"
} )({
  name: "4jxctt",
  styles: "width:16px;height:16px;color:rgba(51, 51, 51, 1)"
} );
var Content = createStyled(DialogContent, {
  target: "e45wfhi1"
} )("padding:0;font-size:", function(_ref22) {
  var theme = _ref22.theme;
  return theme.ketcher.font.size.medium;
}, ";line-height:17px;color:#000000;", function(_ref3) {
  var theme = _ref3.theme;
  return scrollbarThin(theme);
}, ";" + ("" ));
var Footer = createStyled(DialogActions, {
  target: "e45wfhi0"
} )("height:52px;margin:0;padding:0 12px;border-top:", function(_ref4) {
  var theme = _ref4.theme, withborder = _ref4.withborder;
  return withborder === "true" ? theme.ketcher.border.small : "none";
}, ";justify-content:flex-end;.MuiButtonBase-root{border-radius:4px;font-size:", function(_ref5) {
  var theme = _ref5.theme;
  return theme.ketcher.font.size.regular;
}, ";}" + ("" ));
var Modal = function Modal2(_ref6) {
  var children2 = _ref6.children, title = _ref6.title, isOpen = _ref6.isOpen, _ref6$showCloseButton = _ref6.showCloseButton, showCloseButton = _ref6$showCloseButton === void 0 ? true : _ref6$showCloseButton, _ref6$showExpandButto = _ref6.showExpandButton, showExpandButton = _ref6$showExpandButto === void 0 ? false : _ref6$showExpandButto, onClose = _ref6.onClose, className = _ref6.className, modalWidth = _ref6.modalWidth, _ref6$expanded = _ref6.expanded, expanded = _ref6$expanded === void 0 ? false : _ref6$expanded, _ref6$setExpanded = _ref6.setExpanded, setExpanded = _ref6$setExpanded === void 0 ? EmptyFunction : _ref6$setExpanded, testId = _ref6.testId, hideHeaderBorder = _ref6.hideHeaderBorder;
  var theme = useTheme$2();
  var paperProps = reactExports.useMemo(function() {
    return _objectSpread$i(_objectSpread$i({}, testId ? {
      testid: testId
    } : {}), {}, {
      "data-testid": testId,
      style: _objectSpread$i({
        background: theme.ketcher.color.background.primary,
        borderRadius: "8px",
        color: theme.ketcher.color.text.primary
      }, showExpandButton && {
        margin: "auto",
        width: expanded ? "100%" : modalWidth,
        height: expanded ? "100%" : void 0,
        maxWidth: "calc(min(1280px, 100%))",
        maxHeight: "calc(min(980px, 100%))"
      })
    });
  }, [testId, theme.ketcher.color.text.primary, theme.ketcher.color.background.canvas, expanded]);
  var backdropProps = reactExports.useMemo(function() {
    return {
      style: {
        background: theme.ketcher.color.background.overlay,
        opacity: 0.4
      }
    };
  }, [theme.ketcher.color.background.overlay]);
  var subcomponents = {
    Content: null,
    Footer: null
  };
  React__default.Children.forEach(children2, function(child) {
    if (child.type === Content) {
      subcomponents.Content = child;
    } else if (child.type === Footer) {
      subcomponents.Footer = child;
    }
  });
  return jsxs(StyledDialog, {
    BackdropProps: backdropProps,
    PaperProps: paperProps,
    open: isOpen,
    onClose,
    container: document.querySelector(KETCHER_MACROMOLECULES_ROOT_NODE_SELECTOR),
    disableEscapeKeyDown: !showCloseButton,
    className,
    sx: {
      padding: "24px"
    },
    children: [title || showCloseButton || showExpandButton ? jsxs(Header$1, {
      hideborder: hideHeaderBorder,
      children: [jsx(Title, {
        children: title
      }), jsxs("span", {
        children: [showExpandButton && jsx(IconButton$1, {
          title: expanded ? "Minimize window" : "Expand window",
          "data-testid": "expand-window-button",
          className: styles$2.expandButton,
          onClick: function onClick() {
            setExpanded(!expanded);
          },
          children: jsx(StyledIcon$1, {
            name: expanded ? "minimize-expansion" : "expand"
          })
        }), showCloseButton && jsx(IconButton$1, {
          title: "Close window",
          onClick: onClose,
          "data-testid": "close-window-button",
          children: jsx(StyledIcon$1, {
            name: "close"
          })
        })]
      })]
    }) : "", subcomponents.Content, subcomponents.Footer]
  });
};
Modal.Content = Content;
Modal.Footer = Footer;
var _excluded$3 = ["label", "clickHandler", "children", "styleType"];
function ownKeys$h(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$h(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$h(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$h(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var baseButtonStyle = {
  name: "zlt300",
  styles: "padding:5px 8px;border-radius:2px;text-transform:none;line-height:14px;font-size:12px;text-align:center;&.MuiButtonBase-root{width:unset;min-width:70px;}"
} ;
var PrimaryButton = createStyled(ButtonBase, {
  target: "ejign8b1"
} )(function(_ref3) {
  var theme = _ref3.theme;
  return {
    backgroundColor: theme.ketcher.color.button.primary.active,
    border: "1px solid ".concat(theme.ketcher.color.button.primary.active),
    color: "rgb(245, 245, 245)",
    fontWeight: theme.ketcher.font.weight.regular,
    width: "62px",
    height: "24px",
    "&:hover": {
      backgroundColor: theme.ketcher.color.button.primary.hover
    },
    "&:disabled": {
      background: theme.ketcher.color.button.primary.disabled,
      border: "1px solid transparent",
      opacity: 0.4
    }
  };
}, baseButtonStyle, "" );
var SecondaryButton = createStyled(ButtonBase, {
  target: "ejign8b0"
} )(function(_ref22) {
  var theme = _ref22.theme;
  return {
    backgroundColor: "transparent",
    border: "1px solid ".concat(theme.ketcher.color.button.secondary.active),
    color: theme.ketcher.color.button.secondary.active,
    fontWeight: theme.ketcher.font.weight.regular,
    width: "72px",
    height: "24px",
    "&:hover": {
      border: "1px solid ".concat(theme.ketcher.color.button.secondary.hover),
      color: theme.ketcher.color.button.secondary.hover
    },
    "&:disabled": {
      border: "1px solid ".concat(theme.ketcher.color.button.secondary.disabled),
      color: theme.ketcher.color.button.secondary.disabled
    },
    "&:clicked": {
      border: "1px solid ".concat(theme.ketcher.color.button.secondary.clicked),
      color: theme.ketcher.color.button.secondary.clicked
    }
  };
}, baseButtonStyle, "" );
var ActionButton = function ActionButton2(_ref3) {
  var label = _ref3.label, clickHandler = _ref3.clickHandler, children2 = _ref3.children, styleType = _ref3.styleType, rest = _objectWithoutProperties(_ref3, _excluded$3);
  return styleType === "secondary" ? jsx(SecondaryButton, _objectSpread$h(_objectSpread$h({
    onClick: clickHandler,
    title: rest.title || label
  }, rest), {}, {
    children: children2 || label
  })) : jsx(PrimaryButton, _objectSpread$h(_objectSpread$h({
    onClick: clickHandler,
    title: rest.title || label
  }, rest), {}, {
    children: children2 || label
  }));
};
var RnaAccordionContainer = createStyled("div", {
  target: "e117eqk622"
} )({
  name: "uawiic",
  styles: "display:flex;flex-direction:column;justify-content:flex-start;overflow:hidden;height:100%"
} );
var StyledAccordion = createStyled(Accordion$1, {
  target: "e117eqk621"
} )({
  name: "u6kpdv",
  styles: "min-height:32px"
} );
var StyledAccordionWrapper = createStyled("div", {
  target: "e117eqk620"
} )({
  name: "isibqt",
  styles: "flex-grow:2;display:flex;flex-direction:column;min-height:0;>div{overflow:visible;display:flex;flex-direction:column;min-height:0;>div+div{overflow:visible;display:flex;flex-direction:column;min-height:0;flex:1 1 auto;}}"
} );
var PresetsScrollArea = createStyled("div", {
  target: "e117eqk619"
} )({
  name: "1gdm1f0",
  styles: "flex:1 1 auto;min-height:0;overflow-y:auto;overflow-x:hidden"
} );
var DetailsContainer = createStyled("div", {
  target: "e117eqk618"
} )("position:relative;width:100%;display:flex;flex-direction:column;gap:8px;justify-content:start;padding:", function(_ref3) {
  var compact = _ref3.compact;
  return compact ? "4px" : "8px";
}, ";", function(_ref22) {
  var compact = _ref22.compact;
  return compact ? "" : "flex: 1 1 auto; min-height: 0;";
}, ";" + ("" ));
var RnaTabContent = createStyled("div", {
  target: "e117eqk617"
} )({
  name: "6imefc",
  styles: "flex-grow:1;min-height:0;background-color:#f7f9fa;border-radius:4px;margin:4px 8px;padding:4px;&.first-tab{border-radius:0 4px 4px 4px;}&.last-tab{border-radius:4px 0 4px 4px;}"
} );
var CompactDetailsContainer = createStyled("div", {
  target: "e117eqk616"
} )("height:100%;background-color:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.color.tab.content;
}, ";border-radius:2px;overflow:auto;" + ("" ));
var StyledButton$2 = createStyled(Button, {
  target: "e117eqk615"
} )("background-color:", function(_ref4) {
  var theme = _ref4.theme;
  return theme.ketcher.color.button.transparent.active;
}, ";color:", function(_ref5) {
  var theme = _ref5.theme;
  return theme.ketcher.color.text.light;
}, ";border-color:", function(_ref6) {
  var theme = _ref6.theme;
  return theme.ketcher.color.text.light;
}, ";" + ("" ));
var PresetToolbar = createStyled("div", {
  target: "e117eqk614"
} )({
  name: "388a8c",
  styles: "position:relative;display:flex;flex-direction:row;align-items:center;justify-content:flex-start;gap:8px;width:100%"
} );
var NewPresetButton = createStyled(StyledButton$2, {
  target: "e117eqk613"
} )({
  name: "1uga7aq",
  styles: "height:24px;border-radius:4px;font-size:12px"
} );
var FilterIconButton = createStyled("button", {
  target: "e117eqk612"
} )("position:relative;display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;padding:0;margin-left:auto;background-color:transparent;border:none;border-radius:4px;cursor:pointer;color:#333333;>svg{width:16px;height:16px;}", function(_ref7) {
  var hasIndicator = _ref7.hasIndicator, theme = _ref7.theme;
  return hasIndicator ? "\n    &::after {\n      content: '';\n      position: absolute;\n      top: 5px;\n      right: 5px;\n      width: 6px;\n      height: 6px;\n      border-radius: 50%;\n      border: 1px solid #E1E5EA;\n      background-color: ".concat(theme.ketcher.color.button.primary.active, ";\n    }\n  ") : "";
}, ";" + ("" ));
var FilterPopup = createStyled("div", {
  target: "e117eqk611"
} )("position:absolute;top:calc(100% + 4px);right:0;z-index:10;display:flex;flex-direction:column;min-width:160px;padding:4px;background-color:#ffffff;border:1px solid #cad3dd;border-radius:4px;box-shadow:0 4px 12px rgba(0, 0, 0, 0.12);font-size:12px;color:", function(_ref8) {
  var theme = _ref8.theme;
  return theme.ketcher.color.text.primary;
}, ";" + ("" ));
var FilterPopupOption = createStyled("label", {
  target: "e117eqk610"
} )({
  name: "nwcyk",
  styles: "display:flex;align-items:center;gap:5px;cursor:pointer;user-select:none;margin-left:6px;margin-top:10px"
} );
var StyledCheckboxInput = createStyled("input", {
  target: "e117eqk69"
} )({
  name: "gwlugh",
  styles: `position:absolute;opacity:0;cursor:pointer;&+span{display:inline-block;width:16px;height:16px;vertical-align:middle;background-image:url("data:image/svg+xml,%3Csvg width='16' height='16' viewBox='0 0 16 16' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Crect x='0.5' y='0.5' width='15' height='15' rx='3.5' fill='white' stroke='%23B4B9D6'/%3E%3C/svg%3E%0A");background-repeat:no-repeat;background-size:100%;}&:checked+span{background-image:url("data:image/svg+xml,%3Csvg width='16' height='16' viewBox='0 0 16 16' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Crect width='16' height='16' rx='4' fill='%23167782'/%3E%3Cpath d='M6.33711 11.8079L2.42578 7.63124L3.39911 6.71991L6.36845 9.89124L12.6171 3.64258L13.5598 4.58524L6.33711 11.8079Z' fill='white'/%3E%3C/svg%3E%0A");}`
} );
var FilterPopupTitle = createStyled("div", {
  target: "e117eqk68"
} )("font-size:12px;font-weight:400;letter-spacing:0.4px;margin:5px 0 5px 2px;color:", function(_ref9) {
  var theme = _ref9.theme;
  return theme.ketcher.color.text.primary;
}, ";" + ("" ));
var FilterPopupSeparator = createStyled("hr", {
  target: "e117eqk67"
} )({
  name: "vs4chz",
  styles: "width:100%;height:1px;margin:8px 0 4px;border:none;background-color:#e1e5ea"
} );
var FilterPopupActions = createStyled("div", {
  target: "e117eqk66"
} )({
  name: "jhfq5e",
  styles: "display:flex;flex-direction:row;justify-content:flex-end;gap:8px;margin-top:4px"
} );
var FilterPopupActionButton = createStyled(ActionButton, {
  target: "e117eqk65"
} )({
  name: "efr2h1",
  styles: "&.MuiButtonBase-root{width:auto;min-width:unset;padding-left:7px;padding-right:7px;border-radius:4px;}"
} );
var FilterPopupResetButton = createStyled(FilterPopupActionButton, {
  target: "e117eqk64"
} )({
  name: "syzhjw",
  styles: "&.MuiButtonBase-root{border:none;margin-right:auto;padding-left:0;margin-left:6px;color:#167782;}"
} );
var DisabledArea = createStyled("div", {
  target: "e117eqk63"
} )({
  name: "1q5khk2",
  styles: "width:100%;height:100%;background-color:#eff2f594;position:absolute;top:0;left:0"
} );
var RnaTabsContainer = createStyled("div", {
  target: "e117eqk62"
} )({
  name: "bimmx8",
  styles: "display:flex;justify-content:space-between;gap:8px;padding:6px 8px 0"
} );
var RnaTabWrapper = createStyled("div", {
  target: "e117eqk61"
} )({
  name: "qnk899",
  styles: "position:relative;display:flex;align-items:center;&.rna-tab--selected{& button{border-radius:4px 4px 0 0;background-color:#f7f9fa;}&::after{content:'';position:absolute;bottom:-4px;left:0;right:0;height:8px;background-color:#f7f9fa;}}"
} );
var RnaTab = createStyled(Tab, {
  target: "e117eqk60"
} )("height:24px;min-height:24px;min-width:24px;", function(_ref0) {
  var selected = _ref0.selected;
  return selected ? "min-width: 104px;" : "";
}, " display:flex;flex-direction:row;gap:4px;align-items:center;justify-content:center;padding:4px;", function(_ref1) {
  var selected = _ref1.selected;
  return selected ? "margin-top: -8px;" : "";
}, " font-weight:400;font-size:10px;border-radius:4px;background-color:white;opacity:", function(_ref10) {
  var selected = _ref10.selected;
  return selected ? 1 : 0.6;
}, ";text-transform:none;&:hover{background-color:#f3f8f9;}>svg{height:16px;width:16px;color:#b4b9d6;&.MuiTab-iconWrapper{margin:0;}}" + ("" ));
function ownKeys$g(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$g(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$g(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$g(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var useGroupsData = function useGroupsData2(libraryName) {
  var monomers = useAppSelector(selectFilteredMonomers);
  var presets = useAppSelector(selectFilteredPresets);
  var items = selectMonomersInCategory(monomers, libraryName);
  var groups = selectMonomerGroups(items);
  var nucleotideItems = selectUnsplitNucleotides(monomers);
  var nucleotideGroups = selectMonomerGroups(nucleotideItems);
  return reactExports.useMemo(function() {
    return [{
      groupName: RnaBuilderPresetsItem.Presets,
      iconName: "preset",
      groups: [{
        groupItems: presets
      }]
    }, {
      groupName: MonomerGroups.SUGARS,
      iconName: "sugar",
      groups: groups.map(function(group) {
        return _objectSpread$g(_objectSpread$g({}, group), {}, {
          groupItems: group.groupItems.filter(function(item) {
            var _item$props;
            return ((_item$props = item.props) === null || _item$props === void 0 ? void 0 : _item$props.MonomerClass) === KetMonomerClass.Sugar;
          })
        });
      }).filter(function(group) {
        return group.groupItems.length;
      })
    }, {
      groupName: MonomerGroups.BASES,
      iconName: "base",
      groups: groups.map(function(group) {
        return _objectSpread$g(_objectSpread$g({}, group), {}, {
          groupItems: group.groupItems.filter(function(item) {
            var _item$props2;
            return ((_item$props2 = item.props) === null || _item$props2 === void 0 ? void 0 : _item$props2.MonomerClass) === KetMonomerClass.Base;
          })
        });
      }).filter(function(group) {
        return group.groupItems.length;
      })
    }, {
      groupName: MonomerGroups.PHOSPHATES,
      iconName: "phosphate",
      groups: groups.map(function(group) {
        return _objectSpread$g(_objectSpread$g({}, group), {}, {
          groupItems: group.groupItems.filter(function(item) {
            var _item$props3;
            return ((_item$props3 = item.props) === null || _item$props3 === void 0 ? void 0 : _item$props3.MonomerClass) === KetMonomerClass.Phosphate;
          })
        });
      }).filter(function(group) {
        return group.groupItems.length;
      })
    }, {
      groupName: MonomerGroups.NUCLEOTIDES,
      iconName: "nucleotide",
      groups: nucleotideGroups
    }];
  }, [groups, presets, nucleotideGroups]);
};
function ownKeys$f(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$f(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$f(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$f(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var DEFAULT_FILTER = {
  fivePrime: false,
  threePrime: false,
  noPhosphate: false
};
var PresetPhosphateFilterPopup = function PresetPhosphateFilterPopup2(_ref3) {
  var onClose = _ref3.onClose;
  var dispatch2 = useDispatch();
  var currentFilter = useAppSelector(selectPresetPhosphateFilter);
  var _useState = reactExports.useState(currentFilter), _useState2 = _slicedToArray(_useState, 2), draftFilter = _useState2[0], setDraftFilter = _useState2[1];
  var popupRef = reactExports.useRef(null);
  reactExports.useEffect(function() {
    var handleMouseDown = function handleMouseDown2(event) {
      var target = event.target;
      if (popupRef.current && target && popupRef.current.contains(target)) {
        return;
      }
      if (target instanceof Element && target.closest('[data-testid="preset-filter-button"]')) {
        return;
      }
      onClose();
    };
    var handleKeyDown = function handleKeyDown2(event) {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return function() {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);
  var toggle = function toggle2(key) {
    return function() {
      setDraftFilter(function(prev) {
        return _objectSpread$f(_objectSpread$f({}, prev), {}, _defineProperty$1({}, key, !prev[key]));
      });
    };
  };
  var handleResetAll = function handleResetAll2() {
    setDraftFilter(DEFAULT_FILTER);
    dispatch2(setPresetPhosphateFilter2(DEFAULT_FILTER));
    onClose();
  };
  var handleSet = function handleSet2() {
    dispatch2(setPresetPhosphateFilter2(draftFilter));
    onClose();
  };
  return jsxs(FilterPopup, {
    ref: popupRef,
    "data-testid": "preset-phosphate-filter-popup",
    onClick: function onClick(event) {
      return event.stopPropagation();
    },
    children: [jsx(FilterPopupTitle, {
      children: "Filter"
    }), jsxs(FilterPopupOption, {
      children: [jsx(StyledCheckboxInput, {
        type: "checkbox",
        checked: draftFilter.fivePrime,
        onChange: toggle("fivePrime"),
        "data-testid": "preset-filter-5-phosphate"
      }), jsx("span", {}), " 5'-phosphate"]
    }), jsxs(FilterPopupOption, {
      children: [jsx(StyledCheckboxInput, {
        type: "checkbox",
        checked: draftFilter.threePrime,
        onChange: toggle("threePrime"),
        "data-testid": "preset-filter-3-phosphate"
      }), jsx("span", {}), " 3'-phosphate"]
    }), jsxs(FilterPopupOption, {
      children: [jsx(StyledCheckboxInput, {
        type: "checkbox",
        checked: draftFilter.noPhosphate,
        onChange: toggle("noPhosphate"),
        "data-testid": "preset-filter-no-phosphate"
      }), jsx("span", {}), " No phosphate group"]
    }), jsx(FilterPopupSeparator, {}), jsxs(FilterPopupActions, {
      children: [jsx(FilterPopupResetButton, {
        styleType: "secondary",
        label: "Reset all",
        clickHandler: handleResetAll,
        "data-testid": "preset-filter-reset"
      }), jsx(FilterPopupActionButton, {
        label: "Set",
        clickHandler: handleSet,
        "data-testid": "preset-filter-set"
      })]
    })]
  });
};
var RnaElementsTabsView = function RnaElementsTabsView2(_ref3) {
  var activeRnaBuilderItem = _ref3.activeRnaBuilderItem, groupsData = _ref3.groupsData, onNewPresetClick = _ref3.onNewPresetClick, onSelectItem = _ref3.onSelectItem, duplicatePreset = _ref3.duplicatePreset, editPreset = _ref3.editPreset, libraryName = _ref3.libraryName;
  var dispatch2 = useDispatch();
  var presets = useAppSelector(selectFilteredPresets);
  var monomers = useAppSelector(selectFilteredMonomers);
  var isEditMode = useAppSelector(selectIsEditMode);
  var isActivePresetNewAndEmpty = useAppSelector(selectIsActivePresetNewAndEmpty);
  var activeMonomerKey = useAppSelector(selectActiveMonomerKey);
  var presetPhosphateFilter = useAppSelector(selectPresetPhosphateFilter);
  var isFilterActive = Boolean((presetPhosphateFilter === null || presetPhosphateFilter === void 0 ? void 0 : presetPhosphateFilter.fivePrime) || (presetPhosphateFilter === null || presetPhosphateFilter === void 0 ? void 0 : presetPhosphateFilter.threePrime) || (presetPhosphateFilter === null || presetPhosphateFilter === void 0 ? void 0 : presetPhosphateFilter.noPhosphate));
  var _useState = reactExports.useState(false), _useState2 = _slicedToArray(_useState, 2), isFilterOpen = _useState2[0], setIsFilterOpen = _useState2[1];
  return jsxs(Fragment, {
    children: [jsx(RnaTabsContainer, {
      children: groupsData.map(function(groupData) {
        var groupName = groupData.groupName, groups = groupData.groups, iconName = groupData.iconName;
        var selected = groupName === activeRnaBuilderItem;
        var variantMonomers = selectAmbiguousMonomersInCategory(monomers, groupName);
        var quantity = [].concat(_toConsumableArray(groups), _toConsumableArray(variantMonomers)).reduce(function(acc, group) {
          return acc + (group.groupItems.length || 0);
        }, 0);
        var caption = selected ? "".concat(groupName, " (").concat(quantity, ")") : null;
        return jsx(RnaTabWrapper, {
          className: clsx$2(selected && "rna-tab--selected"),
          children: jsx(RnaTab, {
            label: caption,
            title: groupName,
            selected,
            icon: jsx(Icon, {
              name: iconName
            }),
            onClick: function onClick() {
              return dispatch2(setActiveRnaBuilderItem2(groupName));
            },
            "data-testid": "summary-".concat(groupName)
          })
        }, groupName);
      })
    }), groupsData.map(function(groupData) {
      var groupName = groupData.groupName, groups = groupData.groups;
      if (groupName !== activeRnaBuilderItem) {
        return null;
      }
      var variantMonomers = selectAmbiguousMonomersInCategory(monomers, groupName);
      var details = groupName === RnaBuilderPresetsItem.Presets ? jsxs(DetailsContainer, {
        compact: true,
        children: [jsxs(PresetToolbar, {
          children: [jsx(NewPresetButton, {
            onClick: onNewPresetClick,
            "data-testid": "new-preset-button",
            children: "Add new"
          }), jsx(FilterIconButton, {
            type: "button",
            active: isFilterOpen,
            hasIndicator: isFilterActive,
            onClick: function onClick(event) {
              event.stopPropagation();
              setIsFilterOpen(function(prev) {
                return !prev;
              });
            },
            "aria-label": "Filter presets by phosphate position",
            "data-testid": "preset-filter-button",
            children: jsx(Icon, {
              name: "filter"
            })
          }), isFilterOpen && jsx(PresetPhosphateFilterPopup, {
            onClose: function onClose() {
              return setIsFilterOpen(false);
            }
          })]
        }), jsx(RnaPresetGroup, {
          duplicatePreset,
          editPreset,
          presets
        }), isEditMode && !isActivePresetNewAndEmpty && jsx(DisabledArea, {})]
      }) : jsx(DetailsContainer, {
        compact: true,
        children: jsxs(Fragment, {
          children: [groups.map(function(_ref22) {
            var groupItems = _ref22.groupItems, groupTitle = _ref22.groupTitle;
            return jsx(MonomerGroup, {
              title: [MonomerGroups.BASES, MonomerGroups.NUCLEOTIDES].includes(groupName) || groups.length > 1 ? groupTitle : void 0,
              groupName,
              items: groupItems,
              selectedMonomerUniqueKey: activeMonomerKey,
              onItemClick: function onItemClick(monomer) {
                return onSelectItem(monomer, groupName);
              }
            }, groupTitle);
          }), variantMonomers.map(function(_ref32) {
            var groupTitle = _ref32.groupTitle, groupItems = _ref32.groupItems;
            return jsx(MonomerGroup, {
              title: groupTitle,
              items: groupItems,
              libraryName,
              selectedMonomerUniqueKey: activeMonomerKey,
              onItemClick: function onItemClick(monomer) {
                return onSelectItem(monomer, groupName);
              }
            }, groupTitle);
          })]
        })
      });
      var firstTabSelected = activeRnaBuilderItem === RnaBuilderPresetsItem.Presets;
      var lastTabSelected = activeRnaBuilderItem === MonomerGroups.NUCLEOTIDES;
      return jsx(RnaTabContent, {
        className: clsx$2(firstTabSelected && "first-tab", lastTabSelected && "last-tab"),
        children: jsx(CompactDetailsContainer, {
          children: details
        })
      }, groupName);
    })]
  });
};
var RnaElementsTabsView$1 = reactExports.memo(RnaElementsTabsView);
var Summary = function Summary2(_ref3) {
  var groupName = _ref3.groupName, quantity = _ref3.quantity, expanded = _ref3.expanded, iconName = _ref3.iconName;
  return jsxs(SummaryContainer, {
    "data-testid": "summary-".concat(groupName),
    children: [jsx(StyledIcon$2, {
      name: iconName
    }), jsxs(SummaryText, {
      children: [groupName, " (", quantity, ")"]
    }), jsx(StyledIcon$2, {
      name: "chevron",
      expanded
    })]
  });
};
var RnaElementsAccordionView = function RnaElementsAccordionView2(_ref3) {
  var activeRnaBuilderItem = _ref3.activeRnaBuilderItem, groupsData = _ref3.groupsData, newPreset = _ref3.newPreset, onNewPresetClick = _ref3.onNewPresetClick, onSelectItem = _ref3.onSelectItem, duplicatePreset = _ref3.duplicatePreset, editPreset = _ref3.editPreset, libraryName = _ref3.libraryName;
  var dispatch2 = useDispatch();
  var presets = useAppSelector(selectFilteredPresets);
  var monomers = useAppSelector(selectFilteredMonomers);
  var isEditMode = useAppSelector(selectIsEditMode);
  var isActivePresetNewAndEmpty = useAppSelector(selectIsActivePresetNewAndEmpty);
  var activeMonomerKey = useAppSelector(selectActiveMonomerKey);
  var presetPhosphateFilter = useAppSelector(selectPresetPhosphateFilter);
  var isFilterActive = Boolean((presetPhosphateFilter === null || presetPhosphateFilter === void 0 ? void 0 : presetPhosphateFilter.fivePrime) || (presetPhosphateFilter === null || presetPhosphateFilter === void 0 ? void 0 : presetPhosphateFilter.threePrime) || (presetPhosphateFilter === null || presetPhosphateFilter === void 0 ? void 0 : presetPhosphateFilter.noPhosphate));
  var _useState = reactExports.useState(activeRnaBuilderItem), _useState2 = _slicedToArray(_useState, 2), expandedAccordion = _useState2[0], setExpandedAccordion = _useState2[1];
  var _useState3 = reactExports.useState(false), _useState4 = _slicedToArray(_useState3, 2), isFilterOpen = _useState4[0], setIsFilterOpen = _useState4[1];
  var handleAccordionSummaryClick = function handleAccordionSummaryClick2(rnaBuilderItem) {
    if (expandedAccordion === rnaBuilderItem) {
      setExpandedAccordion(null);
    } else {
      setExpandedAccordion(rnaBuilderItem);
      dispatch2(recalculateRnaBuilderValidations2({
        rnaPreset: newPreset,
        isEditMode
      }));
    }
  };
  reactExports.useEffect(function() {
    setExpandedAccordion(activeRnaBuilderItem);
  }, [activeRnaBuilderItem]);
  return jsx(Fragment, {
    children: groupsData.map(function(groupData) {
      var expanded = expandedAccordion === groupData.groupName;
      var variantMonomers = selectAmbiguousMonomersInCategory(monomers, groupData.groupName);
      var quantity = [].concat(_toConsumableArray(groupData.groups), _toConsumableArray(variantMonomers)).reduce(function(acc, group) {
        return acc + (group.groupItems.length || 0);
      }, 0);
      var summary = jsx(Summary, {
        iconName: groupData.iconName,
        groupName: groupData.groupName,
        quantity,
        expanded
      });
      var details = groupData.groupName === RnaBuilderPresetsItem.Presets ? jsxs(DetailsContainer, {
        children: [jsxs(PresetToolbar, {
          children: [jsx(NewPresetButton, {
            onClick: onNewPresetClick,
            "data-testid": "new-preset-button",
            children: "Add new"
          }), jsx(FilterIconButton, {
            type: "button",
            active: isFilterOpen,
            hasIndicator: isFilterActive,
            onClick: function onClick(event) {
              event.stopPropagation();
              setIsFilterOpen(function(prev) {
                return !prev;
              });
            },
            "aria-label": "Filter presets by phosphate position",
            "data-testid": "preset-filter-button",
            children: jsx(Icon, {
              name: "filter"
            })
          }), isFilterOpen && jsx(PresetPhosphateFilterPopup, {
            onClose: function onClose() {
              return setIsFilterOpen(false);
            }
          })]
        }), jsx(PresetsScrollArea, {
          children: jsx(RnaPresetGroup, {
            duplicatePreset,
            editPreset,
            presets
          })
        }), isEditMode && !isActivePresetNewAndEmpty && jsx(DisabledArea, {})]
      }) : jsx(DetailsContainer, {
        children: jsxs(Fragment, {
          children: [groupData.groups.map(function(_ref22) {
            var groupItems = _ref22.groupItems, groupTitle = _ref22.groupTitle;
            var shouldShowTitle = [MonomerGroups.BASES, MonomerGroups.NUCLEOTIDES, MonomerGroups.PEPTIDES].includes(groupData.groupName);
            return jsx(MonomerGroup, {
              title: shouldShowTitle ? groupTitle : void 0,
              groupName: groupData.groupName,
              items: groupItems,
              selectedMonomerUniqueKey: activeMonomerKey,
              onItemClick: function onItemClick(monomer) {
                return onSelectItem(monomer, groupData.groupName);
              }
            }, groupTitle);
          }), variantMonomers.map(function(group) {
            return jsx(MonomerGroup, {
              title: group.groupTitle,
              items: group.groupItems,
              libraryName,
              selectedMonomerUniqueKey: activeMonomerKey,
              onItemClick: function onItemClick(monomer) {
                return onSelectItem(monomer, groupData.groupName);
              }
            }, group.groupTitle);
          })]
        })
      });
      return groupData.groupName === RnaBuilderPresetsItem.Presets && expanded ? jsx(StyledAccordionWrapper, {
        children: jsx(StyledAccordion, {
          "data-testid": "styled-accordion",
          dataTestIdDetails: "rna-accordion-details-".concat(groupData.groupName),
          summary,
          details,
          expanded,
          onSummaryClick: function onSummaryClick() {
            return handleAccordionSummaryClick(groupData.groupName);
          }
        })
      }, groupData.groupName) : jsx(StyledAccordion, {
        "data-testid": "styled-accordion",
        dataTestIdDetails: "rna-accordion-details-".concat(groupData.groupName),
        summary,
        details,
        expanded,
        onSummaryClick: function onSummaryClick() {
          return handleAccordionSummaryClick(groupData.groupName);
        }
      }, groupData.groupName);
    })
  });
};
var RnaElementsAccordionView$1 = reactExports.memo(RnaElementsAccordionView);
function ownKeys$e(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$e(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$e(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$e(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var RnaElements = function RnaElements2(_ref3) {
  var view = _ref3.view, libraryName = _ref3.libraryName, duplicatePreset = _ref3.duplicatePreset, editPreset = _ref3.editPreset;
  var dispatch2 = useDispatch();
  var activeRnaBuilderItem = useAppSelector(selectActiveRnaBuilderItem);
  var activePreset = useAppSelector(selectActivePreset);
  var isEditMode = useAppSelector(selectIsEditMode);
  var editor = useAppSelector(selectEditor);
  var isSequenceEditInRNABuilderMode = useAppSelector(selectIsSequenceEditInRNABuilderMode);
  var _useState = reactExports.useState(activePreset), _useState2 = _slicedToArray(_useState, 2), newPreset = _useState2[0], setNewPreset = _useState2[1];
  reactExports.useEffect(function() {
    dispatch2(setActiveRnaBuilderItem2(isEditMode && activePreset ? activeRnaBuilderItem : RnaBuilderPresetsItem.Presets));
  }, [isEditMode]);
  var groupsData = useGroupsData(libraryName);
  var handleNewPresetClick = reactExports.useCallback(function() {
    dispatch2(createNewPreset2());
    dispatch2(setActiveRnaBuilderItem2(RnaBuilderPresetsItem.Presets));
    dispatch2(setIsEditMode2(true));
  }, [dispatch2]);
  var handleItemSelection = reactExports.useCallback(function(monomer, groupName) {
    var _monomer$monomers$0$m;
    if (isEditMode) {
      dispatch2(setActiveMonomerKey2(getMonomerUniqueKey(monomer)));
    }
    if (!isSequenceEditInRNABuilderMode && !isEditMode) {
      editor === null || editor === void 0 || editor.events.selectMonomer.dispatch(monomer);
    }
    if (!isEditMode) {
      return;
    }
    var monomerClass = isAmbiguousMonomerLibraryItem(monomer) ? (_monomer$monomers$0$m = monomer.monomers[0].monomerItem.props.MonomerClass) === null || _monomer$monomers$0$m === void 0 ? void 0 : _monomer$monomers$0$m.toLowerCase() : monomer.props.MonomerClass.toLowerCase();
    var currentPreset = _objectSpread$e(_objectSpread$e({}, newPreset), {}, _defineProperty$1({}, monomerClass, monomer));
    setNewPreset(currentPreset);
    dispatch2(setActivePresetMonomerGroup2({
      groupName,
      groupItem: monomer
    }));
    dispatch2(setActiveRnaBuilderItem2(groupName));
  }, [dispatch2, editor, isEditMode, isSequenceEditInRNABuilderMode, newPreset]);
  return jsx(RnaAccordionContainer, {
    "data-testid": "rna-accordion",
    children: view === "tabs" ? jsx(RnaElementsTabsView$1, {
      activeRnaBuilderItem,
      groupsData,
      onNewPresetClick: handleNewPresetClick,
      onSelectItem: handleItemSelection,
      libraryName,
      editPreset,
      duplicatePreset
    }) : jsx(RnaElementsAccordionView$1, {
      activeRnaBuilderItem,
      groupsData,
      newPreset,
      onNewPresetClick: handleNewPresetClick,
      onSelectItem: handleItemSelection,
      libraryName,
      editPreset,
      duplicatePreset
    })
  });
};
var RnaBuilder = function RnaBuilder2(_ref3) {
  var libraryName = _ref3.libraryName, duplicatePreset = _ref3.duplicatePreset, editPreset = _ref3.editPreset;
  var dispatch2 = useAppDispatch();
  var uniqueNameError = useAppSelector(selectUniqueNameError);
  var invalidPresetError = useAppSelector(selectInvalidPresetError);
  var isCompactView = useIsCompactView();
  var closeErrorModal3 = function closeErrorModal4() {
    if (uniqueNameError.length > 0) {
      dispatch2(setUniqueNameError2(""));
    }
    if (invalidPresetError.length > 0) {
      dispatch2(setInvalidPresetError2(""));
    }
  };
  return jsxs(RnaBuilderContainer, {
    children: [jsx(RnaEditor, {
      duplicatePreset
    }), jsx(RnaElements, {
      libraryName,
      duplicatePreset,
      editPreset,
      view: isCompactView ? "tabs" : "accordion"
    }), jsxs(Modal, {
      isOpen: !!uniqueNameError || !!invalidPresetError,
      title: "Error Message",
      onClose: closeErrorModal3,
      children: [jsx(Modal.Content, {
        children: jsxs("div", {
          style: {
            padding: "12px"
          },
          children: [uniqueNameError && 'Preset with name "'.concat(uniqueNameError, '" already exists. Please choose another name.'), invalidPresetError && 'Preset with name "'.concat(invalidPresetError, `" can't be used. Because it is impossible to establish bonds between monomers. Edit it's structure or choose another one.`)]
        })
      }), jsx(Modal.Footer, {
        children: jsx(StyledButton$2, {
          onClick: closeErrorModal3,
          children: "Close"
        })
      })]
    })]
  });
};
var tabsContent = function tabsContent2(duplicatePreset, editPreset) {
  return [{
    caption: FavoriteStarSymbol,
    tooltip: "Favorites",
    component: MonomerList,
    testId: "FAVORITES-TAB",
    props: {
      libraryName: MONOMER_LIBRARY_FAVORITES,
      duplicatePreset,
      editPreset
    }
  }, {
    caption: "Peptides",
    component: MonomerList,
    testId: "PEPTIDES-TAB",
    props: {
      libraryName: MONOMER_TYPES.PEPTIDE
    }
  }, {
    caption: "RNA",
    testId: "RNA-TAB",
    component: RnaBuilder,
    props: {
      libraryName: MONOMER_TYPES.RNA,
      duplicatePreset,
      editPreset
    }
  }, {
    caption: "CHEM",
    component: MonomerList,
    testId: "CHEM-TAB",
    props: {
      libraryName: MONOMER_TYPES.CHEM
    }
  }];
};
function ownKeys$d(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$d(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$d(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$d(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var COPY = "_Copy";
var MonomerLibrary = function MonomerLibrary2(_ref3) {
  var toggleLibraryVisibility = _ref3.toggleLibraryVisibility;
  var presetsRef = reactExports.useRef([]);
  var dispatch2 = useAppDispatch();
  var selectedTabIndex = useAppSelector(selectCurrentTabIndex);
  reactExports.useEffect(function() {
    dispatch2(setSearchFilter2(""));
  }, [dispatch2]);
  useAppSelector(selectAllPresets, function(presets) {
    presetsRef.current = presets;
    return true;
  });
  var filterResults = reactExports.useCallback(function(event) {
    dispatch2(setSearchFilter2(event.target.value));
  }, [dispatch2]);
  var duplicatePreset = reactExports.useCallback(function(preset) {
    var name = "".concat(preset === null || preset === void 0 ? void 0 : preset.name).concat(COPY);
    var presetWithSameName;
    do {
      presetWithSameName = presetsRef.current.find(function(preset2) {
        return preset2.name === name;
      });
      if (presetWithSameName) name += COPY;
    } while (presetWithSameName);
    if (presetWithSameName) {
      dispatch2(setUniqueNameError2(name));
      return;
    }
    var nameToSet = presetWithSameName ? "".concat(name).concat(COPY) : name;
    var duplicatedPreset = _objectSpread$d(_objectSpread$d({}, preset), {}, {
      name: nameToSet,
      nameInList: nameToSet,
      "default": false,
      favorite: false
    });
    dispatch2(setActivePreset2(duplicatedPreset));
    dispatch2(setIsEditMode2(true));
    scrollToSelectedPreset(preset === null || preset === void 0 ? void 0 : preset.name);
  }, [dispatch2]);
  var editPreset = reactExports.useCallback(function(preset) {
    dispatch2(setActivePreset2(preset));
    dispatch2(setIsEditMode2(true));
  }, [dispatch2]);
  var tabs = reactExports.useMemo(function() {
    return tabsContent(duplicatePreset, editPreset);
  }, [duplicatePreset, editPreset]);
  var handleTabChange = reactExports.useCallback(function(_event, newTabIndex) {
    dispatch2(setSelectedTabIndex2(newTabIndex));
  }, [dispatch2]);
  return jsxs(MonomerLibraryContainer, {
    "data-testid": "monomer-library",
    children: [jsxs(MonomerLibraryHeader, {
      children: [jsxs(MonomerLibraryInputContainer, {
        children: [jsx(MonomerLibrarySearchIcon, {
          name: "search"
        }), jsx(MonomerLibraryInput, {
          type: "search",
          "data-testid": "monomer-library-input",
          onChange: filterResults,
          placeholder: "Search by name..."
        })]
      }), jsx(MonomerLibraryToggle$1, {
        title: "Hide library",
        onClick: toggleLibraryVisibility,
        "data-testid": "hide-monomer-library",
        children: jsx(Icon, {
          name: "arrows-right"
        })
      })]
    }), jsx(Tabs$1, {
      tabs,
      selectedTabIndex,
      onChange: handleTabChange
    })]
  });
};
var StyledMonomerLibraryToggle = createStyled("div", {
  target: "emj253a0"
} )(function(_ref3) {
  var theme = _ref3.theme;
  return {
    margin: 0,
    fontSize: theme.ketcher.font.size.regular,
    position: "absolute",
    top: "12px",
    cursor: "pointer",
    visibility: "visible",
    opacity: 1,
    whiteSpace: "nowrap",
    display: "flex",
    alignItems: "center",
    lineHeight: 1,
    userSelect: "none",
    backgroundColor: theme.ketcher.color.button.primary.active,
    color: theme.ketcher.color.button.text.primary,
    right: "12px",
    padding: "10px 8px",
    borderRadius: "4px",
    "& > span": {
      display: "flex",
      justifyContent: "center",
      alignItems: "center",
      "&.icon": {
        marginRight: "2px"
      }
    }
  };
}, "" );
var MonomerLibraryToggle = function MonomerLibraryToggle2(_ref22) {
  var onClick = _ref22.onClick;
  return jsxs(StyledMonomerLibraryToggle, {
    onClick,
    "data-testid": "show-monomer-library",
    children: [jsx("span", {
      className: "icon",
      children: jsx(Icon, {
        name: "arrows-left"
      })
    }), " ", "Show Library"]
  });
};
var LoadContainer = createStyled("div", {
  target: "e10ckbgw0"
} )("display:flex;flex-direction:row;justify-content:space-between;align-items:flex-start;width:40px;height:12px;margin-top:10px;& span{display:inline-block;width:8px;height:8px;border:2px solid ", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.color.spinner;
}, ";border-radius:100%;box-sizing:border-box;&:nth-of-type(1){animation:bounce 1s ease-in-out infinite;}&:nth-of-type(2){animation:bounce 1s ease-in-out 0.33s infinite;}&:nth-of-type(3){animation:bounce 1s ease-in-out 0.66s infinite;}}@keyframes bounce{0%,75%,100%{-webkit-transform:translateY(0);-ms-transform:translateY(0);-o-transform:translateY(0);transform:translateY(0);}25%{-webkit-transform:translateY(-100%);-ms-transform:translateY(-100%);-o-transform:translateY(-100%);transform:translateY(-100%);}}" + ("" ));
var LoadingCircles = function LoadingCircles2() {
  return jsxs(LoadContainer, {
    className: "loading-spinner",
    "data-testid": "loading-spinner",
    children: [jsx("span", {}), jsx("span", {}), jsx("span", {})]
  });
};
var ICON_NAME = "file-thumbnail";
var RootContainer$2 = createStyled("div", {
  target: "ep0evuw1"
} )({
  name: "1btsn9l",
  styles: "width:410px;min-height:23em;flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center"
} );
var FileBox = createStyled("div", {
  target: "ep0evuw0"
} )({
  name: "vbftiw",
  styles: "display:flex;flex-direction:row;align-items:center;svg{margin-right:13px;}p{color:#585858;font-size:16px;line-height:19px;}"
} );
var AnalyzingFile = function AnalyzingFile2(_ref3) {
  var fileName = _ref3.fileName;
  return jsxs(RootContainer$2, {
    children: [fileName && jsxs(FileBox, {
      children: [jsx(Icon, {
        name: ICON_NAME
      }), jsx("p", {
        children: fileName
      })]
    }), jsx(LoadingCircles, {})]
  });
};
var OpenOptionText = createStyled("p", {
  target: "eff4ds61"
} )("font-size:10px;text-transform:uppercase;color:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.color.text.light;
}, ";margin:0;text-align:center;line-height:12px;" + ("" ));
var DisabledText = createStyled("p", {
  target: "eff4ds60"
} )("font-size:10px;margin:0;text-align:center;color:", function(_ref22) {
  var theme = _ref22.theme;
  return theme.ketcher.color.text.primary;
}, ";opacity:50%;line-height:12px;" + ("" ));
var _excluded$2 = ["textLabel", "iconName", "disabled", "disabledText"];
function ownKeys$c(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$c(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$c(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$c(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var baseStyle = {
  width: "100%",
  height: "100%",
  display: "flex",
  alignItems: "center",
  flexDirection: "column",
  justifyContent: "space-between"
};
var StyledIcon = createStyled(Icon, {
  target: "erk2iw52"
} )("filter:", function(_ref3) {
  var disabled = _ref3.disabled;
  return disabled ? "grayscale(1)" : "";
}, ";opacity:", function(_ref22) {
  var disabled = _ref22.disabled;
  return disabled ? "0.6" : "1";
}, ";" + ("" ));
var activeStyle = {
  backgroundColor: "#F8FEFFFF"
};
var ButtonContainer$1 = createStyled("div", {
  target: "erk2iw51"
} )("display:flex;flex-direction:column;align-items:center;&>span{font-size:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.font.size.small;
}, ";color:", function(_ref4) {
  var theme = _ref4.theme;
  return theme.ketcher.color.text.primary;
}, ";opacity:50%;}&>svg{margin-bottom:8px;}" + ("" ));
var DropzoneButton = createStyled("button", {
  target: "erk2iw50"
} )({
  name: "1tt0jw3",
  styles: "all:unset;width:100%;height:100%;display:flex;align-items:center;flex-direction:column;justify-content:space-between;cursor:pointer;&:disabled{cursor:default;}"
} );
var FileDrop = function FileDrop2(_ref5) {
  var textLabel = _ref5.textLabel, iconName = _ref5.iconName, disabled = _ref5.disabled, disabledText = _ref5.disabledText, rest = _objectWithoutProperties(_ref5, _excluded$2);
  var _useDropzone = useDropzone(_objectSpread$c({
    multiple: false,
    noClick: true,
    disabled,
    onFileDialogOpen: function onFileDialogOpen() {
      if (document.fullscreenElement) {
        window.isKetcherFullscreenBeforeFilePicker = true;
      }
    },
    onFileDialogCancel: function onFileDialogCancel() {
      var windowContext = window;
      if (windowContext.isKetcherFullscreenBeforeFilePicker) {
        var _document$documentEle, _document$documentEle2;
        (_document$documentEle = (_document$documentEle2 = document.documentElement).requestFullscreen) === null || _document$documentEle === void 0 || _document$documentEle.call(_document$documentEle2)["catch"](function() {
        });
        windowContext.isKetcherFullscreenBeforeFilePicker = false;
      }
    }
  }, rest)), getRootProps = _useDropzone.getRootProps, getInputProps = _useDropzone.getInputProps, isDragActive = _useDropzone.isDragActive, open = _useDropzone.open;
  var style = reactExports.useMemo(function() {
    return _objectSpread$c(_objectSpread$c({}, baseStyle), isDragActive ? activeStyle : {});
  }, [isDragActive]);
  var handleKeyDown = function handleKeyDown2(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!disabled) {
        open();
      }
    }
  };
  return jsxs(DropzoneButton, _objectSpread$c(_objectSpread$c({}, getRootProps({
    style
  })), {}, {
    role: void 0,
    onClick: open,
    onKeyDown: handleKeyDown,
    tabIndex: disabled ? -1 : 0,
    disabled,
    type: "button",
    children: [jsx("input", _objectSpread$c({}, getInputProps())), jsx(StyledIcon, {
      name: iconName,
      disabled
    }), disabled ? jsx(DisabledText, {
      children: disabledText
    }) : jsxs(Fragment, {
      children: [jsx(ButtonContainer$1, {
        children: textLabel && jsx("span", {
          children: textLabel
        })
      }), jsx(OpenOptionText, {
        children: "Open from file"
      })]
    })]
  }));
};
var ICON_NAMES = {
  PASTE: "open-window-paste-icon",
  FILE: "open-window-upload-icon",
  IMAGE: "image-frame"
};
var RootContainer$1 = createStyled("div", {
  target: "e1035cyz1"
} )({
  name: "h9hj7s",
  styles: "display:flex;flex-direction:row;justify-content:space-between;align-items:flex-start;margin-bottom:20px;&>*{margin-right:18px;}& :last-child{margin-right:0;}"
} );
var DropContainer = createStyled("div", {
  target: "e1035cyz0"
} )("width:128px;height:134px;box-shadow:0 4px 12px rgba(103, 104, 132, 0.18);padding:16px;border-radius:12px;flex:1;display:flex;flex-direction:column;justify-content:space-between;align-items:center;box-sizing:border-box;position:relative;cursor:pointer;&>p{margin-top:6px;text-align:center;}svg{fill:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.color.button.primary.active;
}, ";}" + ("" ));
var OpenOptions = function OpenOptions2(_ref22) {
  var selectClipboard = _ref22.selectClipboard, fileLoadHandler = _ref22.fileLoadHandler, errorHandler3 = _ref22.errorHandler;
  return jsxs(RootContainer$1, {
    children: [jsxs(DropContainer, {
      "data-testid": "paste-from-clipboard-button",
      onClick: selectClipboard,
      children: [jsx(Icon, {
        name: ICON_NAMES.PASTE
      }), jsx(OpenOptionText, {
        children: "Paste from clipboard"
      })]
    }), jsx(DropContainer, {
      "data-testid": "open-from-file-button",
      children: jsx(FileDrop, {
        onDropAccepted: fileLoadHandler,
        onDropRejected: function onDropRejected(e) {
          return errorHandler3("Unable to accept file(s). ".concat(e));
        },
        buttonLabel: "Open from file",
        textLabel: "or drag file here",
        iconName: ICON_NAMES.FILE
      })
    }), jsx(DropContainer, {
      "data-testid": "open-from-image-button",
      children: jsx(FileDrop, {
        accept: "image/*",
        onDropAccepted: fileLoadHandler,
        onDropRejected: function onDropRejected(e) {
          return errorHandler3("Unable to accept file(s). ".concat(e));
        },
        buttonLabel: "Open from image",
        textLabel: "or drag file here",
        iconName: ICON_NAMES.IMAGE,
        disabled: true,
        disabledText: "Image Recognition service is not available"
      })
    })]
  });
};
var StyledTextarea = createStyled("textarea", {
  target: "e1q335jk0"
} )("min-width:430px;padding:12px;width:100%;height:100%;overflow:auto;white-space:pre-wrap;resize:none;box-sizing:border-box;outline:transparent;border:none;color:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.color.input.text.active;
}, ";font-size:", function(_ref22) {
  var theme = _ref22.theme;
  return theme.ketcher.font.size.regular;
}, ";background-color:", function(_ref3) {
  var theme = _ref3.theme, readOnly = _ref3.readOnly;
  return readOnly ? theme.ketcher.color.input.background.disabled : theme.ketcher.color.input.background.primary;
}, ";", function(_ref4) {
  var theme = _ref4.theme;
  return scrollbarThin(theme);
}, ";" + ("" ));
var TextArea = function TextArea2(_ref5) {
  var value = _ref5.value, inputHandler = _ref5.inputHandler, _ref5$readonly = _ref5.readonly, readonly = _ref5$readonly === void 0 ? false : _ref5$readonly, _ref5$selectOnInit = _ref5.selectOnInit, selectOnInit = _ref5$selectOnInit === void 0 ? false : _ref5$selectOnInit, className = _ref5.className, testId = _ref5.testId;
  var textArea = reactExports.useRef(null);
  reactExports.useEffect(function() {
    if (selectOnInit) {
      var _textArea$current;
      (_textArea$current = textArea.current) === null || _textArea$current === void 0 || _textArea$current.select();
    }
  }, [textArea, value, selectOnInit]);
  return jsx(StyledTextarea, {
    value,
    readOnly: readonly,
    onChange: inputHandler && function(event) {
      return inputHandler(event.target.value);
    },
    ref: textArea,
    className,
    "data-testid": testId
  });
};
function ownKeys$b(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$b(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$b(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$b(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var StyledTextField = createStyled(TextArea, {
  target: "e17hogtk0"
} )({
  name: "17fmpnb",
  styles: "width:100%;height:320px"
} );
var ViewSwitcher = function ViewSwitcher2(props) {
  if (props.isAnalyzingFile) {
    return jsx(AnalyzingFile, {
      fileName: props.fileName
    });
  } else {
    switch (props.currentState) {
      case props.states.openOptions:
        return jsx(OpenOptions, _objectSpread$b({}, props));
      case props.states.textEditor:
        return jsx(StyledTextField, _objectSpread$b({
          testId: "open-structure-textarea"
        }, props));
      default:
        return null;
    }
  }
};
function fileOpener() {
  return new Promise(function(resolve, reject) {
    if (globalThis.FileReader) {
      resolve(throughFileReader);
    } else {
      reject(new Error("Your browser does not support opening files locally"));
    }
  });
}
function throughFileReader(file) {
  return new Promise(function(resolve, reject) {
    var rd = new FileReader();
    rd.onload = function() {
      var content = rd.result;
      if (file.msClose) file.msClose();
      resolve(content);
    };
    rd.onerror = function(event) {
      reject(new Error("Failed to read file: ".concat(event.type)));
    };
    rd.readAsText(file, "UTF-8");
  });
}
var MODAL_STATES = {
  openOptions: "openOptions",
  textEditor: "textEditor"
};
var OpenFileWrapper = createStyled("div", {
  target: "efvrr8x1"
} )("position:relative;padding:", function(_ref3) {
  var currentState = _ref3.currentState;
  return currentState === MODAL_STATES.openOptions ? "10px 12px" : "0";
}, ";" + ("" ));
createStyled(ActionButton, {
  target: "efvrr8x0"
} )({
  name: "1tx1l5v",
  styles: "margin-right:auto"
} );
createStyled(Icon, {
  target: "e23iben1"
} )({
  name: "1ux2zfx",
  styles: "fill:#343434"
} );
var ChevronStyled = createStyled(Icon, {
  target: "e23iben0"
} )({
  name: "wpnrak",
  styles: "user-select:none;width:16px;height:1em;display:inline-block;flex-shrink:0;transition:fill 200ms cubic-bezier(0.4, 0, 0.2, 1) 0ms;font-size:1.5rem;position:absolute;right:7px;top:calc(50% - 0.5em);pointer-events:none;fill:#5b6077"
} );
var ChevronIcon = function ChevronIcon2(_ref3) {
  var className = _ref3.className;
  return jsx(ChevronStyled, {
    name: "chevron",
    className
  });
};
function ownKeys$a(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$a(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$a(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$a(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var StyledFormControl = createStyled(FormControl, {
  target: "e944g1i2"
} )({
  name: "1pt8ucq",
  styles: "width:100%;padding:0 8px;& label{font-size:12px;line-height:unset;}"
} );
var _ref = {
  name: "af34ib",
  styles: "background-color:white;border-bottom-left-radius:0;border-bottom-right-radius:0"
} ;
var DropDownSelect = createStyled(Select, {
  target: "e944g1i1"
} )("height:24px;border:1px solid #e1e5ea;border-radius:4px;font-size:12px;background-color:white;", function(_ref22) {
  var open = _ref22.open;
  return open && _ref;
}, " & .MuiSelect-select{padding:0 24px 0 8px;height:100%;display:flex;align-items:center;}& span{", function(_ref3) {
  var theme = _ref3.theme;
  return "font-size: ".concat(theme.ketcher.font.size.regular);
}, ";}& .MuiOutlinedInput-notchedOutline{border:0;}" + ("" ));
var stylesForExpanded$1 = {
  backgroundColor: "white",
  border: "1px solid #5B6077",
  borderTopWidth: "0",
  borderRadius: "0px 0px 2px 2px",
  boxShadow: "0 6px 10px rgba(103, 104, 132, 0.15)"
};
var DropDownItem = createStyled(MenuItem$1, {
  target: "e944g1i0"
} )("display:flex;flex-direction:row;justify-content:space-between;padding:0 8px;height:28px;font-size:12px;&.MuiButtonBase-root:hover{border-left:2px solid #167782;}& .MuiTypography-root{", function(_ref4) {
  var theme = _ref4.theme;
  return "font-size: ".concat(theme.ketcher.font.size.regular);
}, ";}" + ("" ));
var DropDown = function DropDown2(_ref5) {
  var options2 = _ref5.options, currentSelection = _ref5.currentSelection, selectionHandler = _ref5.selectionHandler, className = _ref5.className, label = _ref5.label, testId = _ref5.testId, _ref5$customStylesFor = _ref5.customStylesForExpanded, customStylesForExpanded = _ref5$customStylesFor === void 0 ? {} : _ref5$customStylesFor, _ref5$disabled = _ref5.disabled, disabled = _ref5$disabled === void 0 ? false : _ref5$disabled;
  var _useState = reactExports.useState(false), _useState2 = _slicedToArray(_useState, 2), expanded = _useState2[0], setExpanded = _useState2[1];
  var isFullscreen = !!document.fullscreenElement;
  var portalContainer = isFullscreen ? document.querySelector("#root") : void 0;
  var renderLabelById = function renderLabelById2(value) {
    var selectedOption = options2.filter(function(option) {
      return option.id === value;
    })[0];
    return jsx("span", {
      children: selectedOption.label
    });
  };
  var handleSelection = function handleSelection2(event) {
    selectionHandler(event.target.value);
  };
  var handleExpand = function handleExpand2(event) {
    if (event.type === "keydown") {
      return;
    }
    setExpanded(true);
  };
  var handleCollapse = function handleCollapse2() {
    setExpanded(false);
  };
  return jsxs(StyledFormControl, {
    className,
    children: [label && jsx("label", {
      htmlFor: "fileformat",
      children: "File format:"
    }), jsx(DropDownSelect, {
      value: currentSelection,
      onChange: handleSelection,
      open: expanded,
      onOpen: handleExpand,
      onClose: handleCollapse,
      renderValue: renderLabelById,
      IconComponent: ChevronIcon,
      disabled,
      fullWidth: true,
      "data-testid": testId !== null && testId !== void 0 ? testId : "dropdown-select",
      MenuProps: {
        container: portalContainer,
        PaperProps: {
          style: _objectSpread$a(_objectSpread$a({}, stylesForExpanded$1), customStylesForExpanded)
        },
        MenuListProps: {
          style: {
            padding: "0"
          }
        }
      },
      children: options2.map(function(item) {
        return jsx(DropDownItem, {
          value: item.id,
          "data-testid": "".concat(item.label, "-option"),
          children: jsx(ListItemText, {
            primary: item.label
          })
        }, item.id);
      })
    })]
  });
};
var Form = createStyled("form", {
  target: "el6v3ot5"
} )({
  name: "9pd72t",
  styles: "display:flex;flex-direction:column;height:300px"
} );
var Row = createStyled("div", {
  target: "el6v3ot4"
} )({
  name: "1oj61nw",
  styles: "display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:16px"
} );
var StyledDropdown$1 = createStyled(DropDown, {
  target: "el6v3ot3"
} )(function(_ref3) {
  var theme = _ref3.theme;
  return {
    width: "230px",
    flexShrink: 0,
    "& .MuiOutlinedInput-root:hover:not(.Mui-disabled)": {
      border: "1px solid ".concat(theme.ketcher.color.input.border.hover)
    },
    "& .MuiOutlinedInput-root": {
      border: "1px solid ".concat(theme.ketcher.color.input.border.regular),
      backgroundColor: theme.ketcher.color.background.primary,
      color: theme.ketcher.color.text.primary,
      fontFamily: theme.ketcher.font.family.inter
    }
  };
}, "" );
var stylesForExpanded = {
  border: "none"
};
var Loader$1 = createStyled("div", {
  target: "el6v3ot2"
} )({
  name: "kq43v2",
  styles: "position:absolute;top:0;left:0;width:100%;height:100%;display:flex;justify-content:center;align-items:center;background:#fff"
} );
var SvgPreview = createStyled("div", {
  target: "el6v3ot1"
} )(function(_ref22) {
  var theme = _ref22.theme;
  return {
    height: "100%",
    position: "relative",
    border: "1px solid ".concat(theme.ketcher.color.input.border.regular),
    "& svg": {
      width: "100%",
      height: "100%",
      "& .drawn-structures": {
        "& .monomer": {
          lineHeight: "initial !important"
        }
      }
    }
  };
}, "" );
var PreviewContainer$1 = createStyled("div", {
  target: "el6v3ot0"
} )(function(_ref3) {
  var theme = _ref3.theme;
  return {
    display: "flex",
    flexGrow: 1,
    position: "relative",
    "& button": {
      opacity: 0,
      position: "absolute",
      right: "12px",
      top: "12px",
      borderRadius: "4px",
      padding: "2px",
      width: "28px",
      height: "28px",
      "&:not(:active)": {
        backgroundColor: theme.ketcher.color.background.primary,
        color: theme.ketcher.color.text.primary
      }
    },
    "&:hover button": {
      opacity: 1
    },
    "&:focus-within button": {
      opacity: 0
    },
    "&:focus-within button:hover": {
      opacity: 1
    }
  };
}, "" );
var OpenModal = createStyled(Modal, {
  target: "e1oaegu38"
} )(function(_ref3) {
  var modalWidth = _ref3.modalWidth;
  return "\n    .MuiPaper-root {\n      width: ".concat(modalWidth, ";\n      max-width: ").concat(modalWidth, ";\n    }");
}, "" );
var OpenFooter = createStyled("div", {
  target: "e1oaegu37"
} )({
  name: "kj5rtd",
  styles: "width:100%;display:flex;flex-direction:row;justify-content:space-between;align-items:center"
} );
var FooterSelectorContainer = createStyled("div", {
  target: "e1oaegu36"
} )({
  name: "rpuipy",
  styles: "display:flex;height:24px;font-size:12px"
} );
var StyledDropdown = createStyled(StyledDropdown$1, {
  target: "e1oaegu35"
} )({
  name: "7nflbq",
  styles: "padding:0;font-size:12px;& .MuiSelect-select{display:flex;align-items:center;padding:0 20px 0 8px;padding-right:20px !important;height:100%;}& span{font-size:12px;}"
} );
var FooterFormatSelector = createStyled(StyledDropdown, {
  target: "e1oaegu34"
} )(function() {
  return {
    width: "140px"
  };
}, "" );
var FooterSequenceSelector = createStyled(StyledDropdown, {
  target: "e1oaegu33"
} )({
  name: "16zm0c",
  styles: "width:76px;margin-left:8px"
} );
var FooterPeptideLettersSelector = createStyled(StyledDropdown, {
  target: "e1oaegu32"
} )({
  name: "l4tg7k",
  styles: "width:105px;margin-left:8px"
} );
var FooterButtonContainer = createStyled("div", {
  target: "e1oaegu31"
} )({
  name: "oq6u0f",
  styles: "display:flex;gap:10px"
} );
var FooterButton = createStyled(ActionButton, {
  target: "e1oaegu30"
} )({
  name: "b9l38d",
  styles: "width:min-content"
} );
var KET = "ket";
var SEQ = "seq";
var RNA = "rna";
var PEPTIDE = "peptide";
var FASTA = "fasta";
var ONE_LETTER = "one-letter";
var THREE_LETTER = "three-letter";
var options$1 = [{
  id: "ket",
  label: "Ket Format"
}, {
  id: "mol",
  label: "MDL Molfile V3000"
}, {
  id: "seq",
  label: "Sequence"
}, {
  id: "fasta",
  label: "FASTA"
}, {
  id: "idt",
  label: "IDT"
}, {
  id: "axo-labs",
  label: "AxoLabs"
}, {
  id: "helm",
  label: "HELM"
}, {
  id: "biln",
  label: "BILN"
}];
var additionalOptions = [{
  id: RNA,
  label: "RNA"
}, {
  id: "dna",
  label: "DNA"
}, {
  id: PEPTIDE,
  label: "Peptide"
}];
var peptideLettersFormatOptions = [{
  id: ONE_LETTER,
  label: "1-letter code"
}, {
  id: THREE_LETTER,
  label: "3-letter code"
}];
var inputFormats = macromoleculesFilesInputFormats;
var addToCanvas = function addToCanvas2(_ref22) {
  var ketSerializer = _ref22.ketSerializer, editor = _ref22.editor, struct = _ref22.struct;
  var isCanvasEmptyBeforeOpenStructure = !editor.drawingEntitiesManager.hasDrawingEntities;
  var deserialisedKet = ketSerializer.deserializeToDrawingEntities(struct);
  if (!deserialisedKet) {
    throw new Error("Error during parsing file");
  }
  deserialisedKet.drawingEntitiesManager.centerMacroStructure();
  var _deserialisedKet$draw = deserialisedKet.drawingEntitiesManager.mergeInto(editor.drawingEntitiesManager), modelChanges = _deserialisedKet$draw.command;
  var editorHistory = EditorHistory.getInstance(editor);
  var isSequenceMode = editor.mode.modeName === "sequence-layout-mode";
  var isSnakeMode = editor.mode.modeName === "snake-layout-mode";
  var isFlexMode = editor.mode.modeName === "flex-layout-mode";
  if (isFlexMode) {
    if (editor.drawingEntitiesManager.hasAntisenseChains) {
      modelChanges.merge(editor.drawingEntitiesManager.applySnakeLayout(true, true, true));
      modelChanges.setUndoOperationsByPriority();
    }
  }
  editor.drawingEntitiesManager.detectBondsOverlappedByMonomers();
  editor.renderersContainer.update(modelChanges);
  editorHistory.update(modelChanges);
  if (isSequenceMode) {
    modelChanges.setUndoOperationReverse();
    editor.events.selectMode.dispatch({
      mode: ModeTypes.sequence,
      mergeWithLatestHistoryCommand: true
    });
  }
  if (isSnakeMode) {
    modelChanges.setUndoOperationReverse();
    editor.events.selectMode.dispatch({
      mode: ModeTypes.snake,
      mergeWithLatestHistoryCommand: true
    });
  }
  if (isCanvasEmptyBeforeOpenStructure) {
    editor.zoomToStructuresIfNeeded();
  }
  editor.calculateAndStoreNextAutochainPosition(deserialisedKet.drawingEntitiesManager);
};
var onOk = (function() {
  var _ref4 = _asyncToGenerator(_regeneratorRuntime.mark(function _callee(_ref3) {
    var struct, formatSelection, additionalSelection, peptideLettersFormatSelection, onCloseCallback, setIsLoading, dispatch2, isKet, isSeq, isFasta, ketSerializer, editor, inputFormat, fileData, showParsingError, indigo, ketStruct, stringError;
    return _regeneratorRuntime.wrap(function _callee$(_context) {
      while (1) switch (_context.prev = _context.next) {
        case 0:
          struct = _ref3.struct, formatSelection = _ref3.formatSelection, additionalSelection = _ref3.additionalSelection, peptideLettersFormatSelection = _ref3.peptideLettersFormatSelection, onCloseCallback = _ref3.onCloseCallback, setIsLoading = _ref3.setIsLoading, dispatch2 = _ref3.dispatch;
          isKet = formatSelection === KET;
          isSeq = formatSelection === SEQ;
          isFasta = formatSelection === FASTA;
          ketSerializer = new KetSerializer();
          editor = provideEditorInstance();
          fileData = struct;
          showParsingError = function showParsingError2(stringError2) {
            var errorMessage = "Convert error! " + stringError2;
            dispatch2(openErrorModal2({
              errorMessage,
              errorTitle: isSeq || isFasta ? "Unsupported symbols" : ""
            }));
          };
          if (!isKet) {
            _context.next = 13;
            break;
          }
          try {
            addToCanvas({
              struct,
              ketSerializer,
              editor
            });
            onCloseCallback();
          } catch (e) {
            showParsingError("Error during file parsing.");
          }
          return _context.abrupt("return");
        case 13:
          if (isFasta || isSeq && peptideLettersFormatSelection !== THREE_LETTER) {
            inputFormat = inputFormats[formatSelection][additionalSelection];
            fileData = fileData.toUpperCase();
          } else if (isSeq && peptideLettersFormatSelection === THREE_LETTER) {
            inputFormat = inputFormats.seq.peptide3Letter;
          } else {
            inputFormat = inputFormats[formatSelection];
          }
        case 14:
          indigo = IndigoProvider.getIndigo();
          _context.prev = 15;
          setIsLoading(true);
          _context.next = 19;
          return indigo.convert({
            struct: fileData,
            output_format: ChemicalMimeType$1.KET,
            input_format: inputFormat
          });
        case 19:
          ketStruct = _context.sent;
          addToCanvas({
            struct: ketStruct.struct,
            ketSerializer,
            editor
          });
          onCloseCallback();
          _context.next = 29;
          break;
        case 24:
          _context.prev = 24;
          _context.t0 = _context["catch"](15);
          stringError = normalizeError(_context.t0).message;
          showParsingError(stringError);
          KetcherLogger.error(_context.t0);
        case 29:
          _context.prev = 29;
          setIsLoading(false);
          return _context.finish(29);
        case 32:
        case "end":
          return _context.stop();
      }
    }, _callee, null, [[15, 24, 29, 32]]);
  }));
  return function onOk2(_x) {
    return _ref4.apply(this, arguments);
  };
})();
var isAnalyzingFile = false;
var errorHandler = function errorHandler2(error) {
  return void 0;
};
var Open = function Open2(_ref5) {
  var isModalOpen = _ref5.isModalOpen, onClose = _ref5.onClose;
  var dispatch2 = useAppDispatch();
  var _useState = reactExports.useState(""), _useState2 = _slicedToArray(_useState, 2), structStr = _useState2[0], setStructStr = _useState2[1];
  var _useState3 = reactExports.useState(""), _useState4 = _slicedToArray(_useState3, 2), fileName = _useState4[0], setFileName = _useState4[1];
  var _useState5 = reactExports.useState(false), _useState6 = _slicedToArray(_useState5, 2), isLoading = _useState6[0], setIsLoading = _useState6[1];
  var _useState7 = reactExports.useState(), _useState8 = _slicedToArray(_useState7, 2), opener = _useState8[0], setOpener = _useState8[1];
  var _useState9 = reactExports.useState(MODAL_STATES.openOptions), _useState0 = _slicedToArray(_useState9, 2), currentState = _useState0[0], setCurrentState = _useState0[1];
  var _useState1 = reactExports.useState(KET), _useState10 = _slicedToArray(_useState1, 2), formatSelection = _useState10[0], setFormatSelection = _useState10[1];
  var _useState11 = reactExports.useState(RNA), _useState12 = _slicedToArray(_useState11, 2), additionalSelection = _useState12[0], setAdditionalSelection = _useState12[1];
  var _useState13 = reactExports.useState(ONE_LETTER), _useState14 = _slicedToArray(_useState13, 2), peptideLettersFormatSelection = _useState14[0], setPeptideLettersFormatSelection = _useState14[1];
  reactExports.useEffect(function() {
    var splittedFilenameByDot = fileName === null || fileName === void 0 ? void 0 : fileName.split(".");
    var fileExtension = splittedFilenameByDot[splittedFilenameByDot.length - 1];
    if (fileExtension) {
      var option = options$1.find(function(el) {
        return el.id === fileExtension;
      });
      var id2 = option !== null && option !== void 0 && option.id ? option.id : SEQ;
      setFormatSelection(id2);
    }
  }, [fileName]);
  reactExports.useEffect(function() {
    fileOpener().then(function(chosenOpener) {
      setOpener({
        chosenOpener
      });
    });
  }, []);
  var onCloseCallback = reactExports.useCallback(function() {
    setCurrentState(MODAL_STATES.openOptions);
    setStructStr("");
    setFormatSelection(KET);
    setAdditionalSelection(RNA);
    onClose();
  }, [onClose]);
  var onFileLoad = function onFileLoad2(files) {
    var windowContext = window;
    if (windowContext.isKetcherFullscreenBeforeFilePicker) {
      var _document$documentEle, _document$documentEle2;
      (_document$documentEle = (_document$documentEle2 = document.documentElement).requestFullscreen) === null || _document$documentEle === void 0 || _document$documentEle.call(_document$documentEle2)["catch"](function() {
      });
      windowContext.isKetcherFullscreenBeforeFilePicker = false;
    }
    var onLoad = function onLoad2(fileContent) {
      setStructStr(fileContent);
      setCurrentState(MODAL_STATES.textEditor);
    };
    var onError = function onError2() {
      return errorHandler();
    };
    setFileName(files[0].name);
    opener === null || opener === void 0 || opener.chosenOpener(files[0]).then(onLoad, onError);
  };
  var addToCanvasHandler = function addToCanvasHandler2() {
    onOk({
      struct: structStr,
      formatSelection,
      additionalSelection,
      peptideLettersFormatSelection,
      onCloseCallback,
      setIsLoading,
      dispatch: dispatch2
    });
  };
  var openHandler = function openHandler2() {
    var editor = provideEditorInstance();
    var history = EditorHistory.getInstance(editor);
    var modelChanges = editor.drawingEntitiesManager.deleteAllEntities();
    history.update(modelChanges);
    editor.renderersContainer.update(modelChanges);
    editor.zoomToStructuresIfNeeded();
    onOk({
      struct: structStr,
      formatSelection,
      additionalSelection,
      peptideLettersFormatSelection,
      onCloseCallback,
      setIsLoading,
      dispatch: dispatch2
    });
  };
  var renderFooter = function renderFooter2() {
    return jsxs(OpenFooter, {
      children: [jsxs(FooterSelectorContainer, {
        children: [jsx(FooterFormatSelector, {
          options: options$1,
          currentSelection: formatSelection,
          selectionHandler: setFormatSelection,
          customStylesForExpanded: stylesForExpanded
        }, formatSelection), formatSelection === SEQ || formatSelection === FASTA ? jsx(FooterSequenceSelector, {
          options: additionalOptions,
          currentSelection: additionalSelection,
          selectionHandler: setAdditionalSelection,
          customStylesForExpanded: stylesForExpanded,
          testId: "dropdown-select-type"
        }, additionalSelection) : null, formatSelection === SEQ && additionalSelection === PEPTIDE ? jsx(FooterPeptideLettersSelector, {
          options: peptideLettersFormatOptions,
          currentSelection: peptideLettersFormatSelection,
          selectionHandler: setPeptideLettersFormatSelection,
          testId: "dropdown-select-peptide-letters-format"
        }) : null]
      }), jsxs(FooterButtonContainer, {
        children: [jsx(FooterButton, {
          disabled: !structStr.trim(),
          clickHandler: openHandler,
          label: "Open as New",
          styleType: "secondary",
          "data-testid": "open-as-new-button"
        }, "openButton"), jsx(FooterButton, {
          disabled: !structStr.trim(),
          clickHandler: addToCanvasHandler,
          label: "Add to Canvas",
          title: "Structure will be loaded as fragment and added to Clipboard",
          "data-testid": "add-to-canvas-button"
        }, "copyButton")]
      })]
    });
  };
  return jsxs(OpenModal, {
    isOpen: isModalOpen,
    title: "Open Structure",
    onClose: onCloseCallback,
    modalWidth: currentState === MODAL_STATES.textEditor ? "620px" : "",
    testId: "openStructureModal",
    children: [jsx(Modal.Content, {
      children: jsxs(OpenFileWrapper, {
        currentState,
        children: [jsx(ViewSwitcher, {
          isAnalyzingFile,
          fileName,
          currentState,
          states: MODAL_STATES,
          selectClipboard: function selectClipboard() {
            return setCurrentState(MODAL_STATES.textEditor);
          },
          fileLoadHandler: onFileLoad,
          errorHandler,
          value: structStr,
          inputHandler: setStructStr
        }), isLoading && jsx(Loader$1, {
          children: jsx(LoadingCircles, {})
        })]
      })
    }), currentState === MODAL_STATES.textEditor && !isAnalyzingFile ? jsx(Modal.Footer, {
      withborder: "true",
      children: renderFooter()
    }) : jsx(Fragment, {})]
  });
};
var _excluded$1 = ["value", "id", "onChange", "label", "type", "className", "inputClassName"];
function ownKeys$9(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$9(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$9(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$9(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var Label = createStyled("label", {
  target: "e10m4n7r1"
} )(function(_ref3) {
  var theme = _ref3.theme;
  return {
    display: "flex",
    flexDirection: "column",
    marginRight: "8px",
    color: theme.ketcher.color.text.primary,
    fontSize: "12px"
  };
}, "" );
var Input = createStyled("input", {
  target: "e10m4n7r0"
} )(function(_ref22) {
  var theme = _ref22.theme;
  return {
    height: "24px",
    padding: "3px 7px",
    border: "1px solid ".concat(theme.ketcher.color.input.border.regular),
    fontSize: "14px",
    borderRadius: "4px",
    backgroundColor: theme.ketcher.color.input.background.primary,
    color: theme.ketcher.color.text.primary,
    outline: "transparent",
    width: "164px",
    letterSpacing: "normal",
    "&:active, &:focus": {
      color: theme.ketcher.color.input.text.active
    },
    "&:hover": {
      border: "1px solid ".concat(theme.ketcher.color.input.border.hover)
    }
  };
}, "" );
var TextInputField = function TextInputField2(_ref3) {
  var value = _ref3.value, id2 = _ref3.id, onChange = _ref3.onChange, label = _ref3.label, type = _ref3.type, className = _ref3.className, inputClassName2 = _ref3.inputClassName, rest = _objectWithoutProperties(_ref3, _excluded$1);
  var handleChange = function handleChange2(event) {
    onChange(event.target.value);
  };
  return jsxs(Label, {
    htmlFor: id2,
    className,
    children: [label && jsx("span", {
      children: label
    }), jsx(Input, _objectSpread$9({
      type: type || "text",
      id: id2,
      value,
      className: inputClassName2,
      onChange: handleChange
    }, rest))]
  });
};
var ChemicalMimeType;
(function(ChemicalMimeType2) {
  ChemicalMimeType2["Ket"] = "chemical/x-ket";
  ChemicalMimeType2["Mol"] = "chemical/x-mdl-molfile";
  ChemicalMimeType2["HELM"] = "chemincal/x-helm";
  ChemicalMimeType2["Fasta"] = "chemical/x-fasta";
  ChemicalMimeType2["Sequence"] = "chemical/x-sequence";
  ChemicalMimeType2["Idt"] = "chemical/x-idt";
  ChemicalMimeType2["AxoLabs"] = "chemical/x-axo-labs";
  ChemicalMimeType2["Svg"] = "image/svg+xml";
  ChemicalMimeType2["BILN"] = "chemical/x-biln";
})(ChemicalMimeType || (ChemicalMimeType = {}));
var SupportedFormatProperties = _createClass(function SupportedFormatProperties2(name, mime, extensions, supportsCoords, options2) {
  _classCallCheck(this, SupportedFormatProperties2);
  this.name = name;
  this.mime = mime;
  this.extensions = extensions;
  this.supportsCoords = supportsCoords !== null && supportsCoords !== void 0 ? supportsCoords : false;
  this.options = options2 !== null && options2 !== void 0 ? options2 : {};
});
var formatProperties = {
  ket: new SupportedFormatProperties("Ket file", ChemicalMimeType.Ket, [".ket"], true, {}),
  mol: new SupportedFormatProperties("MDL Molfile V3000", ChemicalMimeType.Mol, [".mol"], true, {
    "molfile-saving-mode": "3000"
  }),
  fasta: new SupportedFormatProperties("FASTA", ChemicalMimeType.Fasta, [".fasta"], false, {}),
  sequence: new SupportedFormatProperties("SEQUENCE", ChemicalMimeType.Sequence, [".seq"], false, {}),
  "sequence-3-letter": new SupportedFormatProperties("SEQUENCE (3-letter code)", ChemicalMimeType.Sequence, [".seq"], false, {}),
  idt: new SupportedFormatProperties("IDT", ChemicalMimeType.Idt, [".idt"], false, {}),
  "axo-labs": new SupportedFormatProperties("AxoLabs", ChemicalMimeType.AxoLabs, [".axolabs"], false, {}),
  helm: new SupportedFormatProperties("HELM", ChemicalMimeType.HELM, [".helm"]),
  biln: new SupportedFormatProperties("BILN", ChemicalMimeType.BILN, [".biln"]),
  svg: new SupportedFormatProperties("SVG Document", ChemicalMimeType.Svg, [".svg"])
};
var getPropertiesByFormat = function getPropertiesByFormat2(format2) {
  return formatProperties[format2];
};
var options = [{
  id: "ket",
  label: "Ket Format"
}, {
  id: "mol",
  label: "MDL Molfile V3000"
}, {
  id: "sequence",
  label: "Sequence (1-letter code)"
}, {
  id: "sequence-3-letter",
  label: "Sequence (3-letter code)"
}, {
  id: "fasta",
  label: "FASTA"
}, {
  id: "idt",
  label: "IDT"
}, {
  id: "axo-labs",
  label: "AxoLabs"
}, {
  id: "svg",
  label: "SVG Document"
}, {
  id: "helm",
  label: "HELM"
}, {
  id: "biln",
  label: "BILN"
}];
var formatDetector = {
  mol: ChemicalMimeType$1.Mol,
  fasta: ChemicalMimeType$1.FASTA,
  sequence: ChemicalMimeType$1.SEQUENCE,
  "sequence-3-letter": ChemicalMimeType$1.PeptideSequenceThreeLetter,
  idt: ChemicalMimeType$1.IDT,
  "axo-labs": ChemicalMimeType$1.AXOLABS,
  helm: ChemicalMimeType$1.HELM,
  biln: ChemicalMimeType$1.BILN
};
var StyledModal$1 = createStyled(Modal, {
  target: "e12csxs60"
} )({
  name: "krpfk5",
  styles: "& div.MuiPaper-root{background:white;min-height:400px;min-width:430px;}& .MuiDialogContent-root{overflow:hidden;height:100%;}"
} );
var Save = function Save2(_ref3) {
  var onClose = _ref3.onClose, isModalOpen = _ref3.isModalOpen;
  var dispatch2 = useAppDispatch();
  var _useState = reactExports.useState("ket"), _useState2 = _slicedToArray(_useState, 2), currentFileFormat = _useState2[0], setCurrentFileFormat = _useState2[1];
  var _useState3 = reactExports.useState("ketcher"), _useState4 = _slicedToArray(_useState3, 2), currentFileName = _useState4[0], setCurrentFileName = _useState4[1];
  var _useState5 = reactExports.useState(""), _useState6 = _slicedToArray(_useState5, 2), struct = _useState6[0], setStruct = _useState6[1];
  var _useState7 = reactExports.useState(false), _useState8 = _slicedToArray(_useState7, 2), isLoading = _useState8[0], setIsLoading = _useState8[1];
  var _useState9 = reactExports.useState(), _useState0 = _slicedToArray(_useState9, 2), svgData = _useState0[0], setSvgData = _useState0[1];
  var indigo = IndigoProvider.getIndigo();
  var editor = provideEditorInstance();
  var handleSelectChange = (function() {
    var _ref22 = _asyncToGenerator(_regeneratorRuntime.mark(function _callee(fileFormat) {
      var ketSerializer, serializedKet, ketcherRootRect, ketcherRootOffsetX, ketcherRootOffsetY, _svgData, isValid, result, stringError, errorMessage;
      return _regeneratorRuntime.wrap(function _callee$(_context) {
        while (1) switch (_context.prev = _context.next) {
          case 0:
            setCurrentFileFormat(fileFormat);
            ketSerializer = new KetSerializer();
            serializedKet = ketSerializer.serialize(editor.drawingEntitiesManager.micromoleculesHiddenEntities.clone(), editor.drawingEntitiesManager);
            setSvgData(void 0);
            if (!(fileFormat === "ket")) {
              _context.next = 7;
              break;
            }
            setStruct(serializedKet);
            return _context.abrupt("return");
          case 7:
            if (!(fileFormat === "svg")) {
              _context.next = 14;
              break;
            }
            ketcherRootRect = editor.ketcherRootElementBoundingClientRect;
            ketcherRootOffsetX = (ketcherRootRect === null || ketcherRootRect === void 0 ? void 0 : ketcherRootRect.x) || 0;
            ketcherRootOffsetY = (ketcherRootRect === null || ketcherRootRect === void 0 ? void 0 : ketcherRootRect.y) || 0;
            _svgData = getSvgFromDrawnStructures(editor.canvas, "preview", {
              horizontal: ketcherRootOffsetX,
              vertical: ketcherRootOffsetY
            });
            setSvgData(_svgData);
            return _context.abrupt("return");
          case 14:
            if (fileFormat === "helm") {
              if (editor.drawingEntitiesManager.molecules.length > 0) {
                editor.events.error.dispatch("The molecule will be exported using inline SMILES, and on load will appear as a CHEM monomer");
              }
              if (!isHelmCompatible(Array.from(editor.drawingEntitiesManager.monomers.values()), editor.monomersLibrary)) {
                editor.events.error.dispatch("Some of the monomers do not have aliases in the HELM Core Library - they are exported using Ketcher aliases.");
              }
            }
            _context.prev = 15;
            setIsLoading(true);
            if (!(fileFormat === "fasta" || fileFormat === "sequence" || fileFormat === "idt")) {
              _context.next = 21;
              break;
            }
            isValid = editor.drawingEntitiesManager.validateIfApplicableForFasta();
            if (isValid) {
              _context.next = 21;
              break;
            }
            throw new Error("Error during sequence type recognition(RNA, DNA or Peptide)");
          case 21:
            _context.next = 23;
            return indigo.convert({
              struct: serializedKet,
              output_format: formatDetector[fileFormat]
            });
          case 23:
            result = _context.sent;
            setStruct(result.struct);
            _context.next = 34;
            break;
          case 27:
            _context.prev = 27;
            _context.t0 = _context["catch"](15);
            if (_context.t0 instanceof Error) {
              stringError = _context.t0.message;
            } else {
              stringError = typeof _context.t0 === "string" ? _context.t0 : JSON.stringify(_context.t0);
            }
            errorMessage = "Convert error! " + stringError;
            dispatch2(openErrorModal2(errorMessage));
            KetcherLogger.error(errorMessage);
            setCurrentFileFormat("ket");
          case 34:
            _context.prev = 34;
            setIsLoading(false);
            return _context.finish(34);
          case 37:
          case "end":
            return _context.stop();
        }
      }, _callee, null, [[15, 27, 34, 37]]);
    }));
    return function handleSelectChange2(_x) {
      return _ref22.apply(this, arguments);
    };
  })();
  var handleInputChange = function handleInputChange2(value) {
    setCurrentFileName(value);
  };
  var handleSave = function handleSave2() {
    var blobPart;
    if (currentFileFormat === "svg") {
      var ketcherRootRect = editor.ketcherRootElementBoundingClientRect;
      var ketcherRootOffsetX = (ketcherRootRect === null || ketcherRootRect === void 0 ? void 0 : ketcherRootRect.x) || 0;
      var ketcherRootOffsetY = (ketcherRootRect === null || ketcherRootRect === void 0 ? void 0 : ketcherRootRect.y) || 0;
      var _svgData2 = getSvgFromDrawnStructures(editor.canvas, "file", {
        horizontal: ketcherRootOffsetX,
        vertical: ketcherRootOffsetY
      });
      if (!_svgData2) {
        onClose();
        return;
      }
      blobPart = _svgData2;
    } else {
      blobPart = struct;
    }
    var blob = new Blob([blobPart], {
      type: getPropertiesByFormat(currentFileFormat).mime
    });
    var formatProperties2 = getPropertiesByFormat(currentFileFormat);
    FileSaver_minExports.saveAs(blob, "".concat(currentFileName).concat(formatProperties2.extensions[0]));
    onClose();
  };
  var handleCopy = function handleCopy2(event) {
    event.preventDefault();
    try {
      if (isClipboardAPIAvailable()) {
        navigator.clipboard.writeText(struct);
      } else {
        legacyCopy(event.clipboardData, {
          "text/plain": struct
        });
      }
    } catch (e) {
      KetcherLogger.error("copyAs.js::copyAs", e);
      dispatch2(openErrorModal2("This feature is not available in your browser"));
    }
  };
  reactExports.useEffect(function() {
    if (currentFileFormat === "ket") {
      var ketSerializer = new KetSerializer();
      var serializedKet = ketSerializer.serialize(editor.drawingEntitiesManager.micromoleculesHiddenEntities.clone(), editor.drawingEntitiesManager);
      setStruct(serializedKet);
    }
  }, [currentFileFormat]);
  return jsxs(StyledModal$1, {
    title: "save structure",
    isOpen: isModalOpen,
    onClose,
    testId: "save-structure-dialog",
    children: [jsx(Modal.Content, {
      children: jsxs(Form, {
        onSubmit: handleSave,
        id: "save",
        children: [jsxs(Row, {
          style: {
            padding: "12px 12px 10px"
          },
          children: [jsx("div", {
            children: jsx(TextInputField, {
              value: currentFileName,
              id: "filename",
              onChange: handleInputChange,
              label: "File name:",
              "data-testid": "filename-input"
            })
          }), jsx(StyledDropdown$1, {
            label: "File format:",
            options,
            currentSelection: currentFileFormat,
            selectionHandler: handleSelectChange,
            customStylesForExpanded: stylesForExpanded,
            testId: "file-format-list"
          })]
        }), svgData ? jsx(SvgPreview, {
          dangerouslySetInnerHTML: {
            __html: svgData
          },
          "data-testid": "preview-area"
        }) : jsxs(PreviewContainer$1, {
          children: [jsx(TextArea, {
            testId: "preview-area",
            value: struct,
            readonly: true
          }), jsx(IconButton, {
            onClick: handleCopy,
            iconName: "copy",
            title: "Copy to clipboard",
            testId: "copy-to-clipboard"
          }), isLoading && jsx(Loader$1, {
            children: jsx(LoadingCircles, {})
          })]
        })]
      })
    }), jsxs(Modal.Footer, {
      children: [jsx(ActionButton, {
        label: "Cancel",
        styleType: "secondary",
        clickHandler: onClose,
        "data-testid": "cancel-button"
      }), jsx(ActionButton, {
        label: "Save",
        clickHandler: handleSave,
        disabled: !currentFileName,
        "data-testid": "save-button"
      })]
    })]
  });
};
var StyledActionButton = createStyled(ActionButton, {
  target: "e1kgbmg80"
} )(function() {
  return {
    width: "72px"
  };
}, "" );
var DeleteTextWrapper = createStyled("div", {
  target: "e11sfr0q0"
} )({
  name: "606i4c",
  styles: "padding:12px"
} );
var Delete = function Delete2(_ref3) {
  var isModalOpen = _ref3.isModalOpen, onClose = _ref3.onClose;
  var dispatch2 = useAppDispatch();
  var activePresetForContextMenu = useAppSelector(selectActivePresetForContextMenu);
  var editor = useAppSelector(selectEditor);
  var onCloseCallback = reactExports.useCallback(function() {
    onClose();
  }, [onClose]);
  var cancelHandler = function cancelHandler2() {
    onCloseCallback();
  };
  var deleteHandler = function deleteHandler2() {
    onCloseCallback();
    dispatch2(deletePreset2(activePresetForContextMenu));
    dispatch2(setIsEditMode2(false));
    dispatch2(createNewPreset2());
    editor === null || editor === void 0 || editor.events.selectPreset.dispatch(null);
  };
  return jsxs(Modal, {
    isOpen: isModalOpen,
    title: "Delete RNA Preset",
    onClose: onCloseCallback,
    "data-testid": "delete-preset-modal",
    children: [jsx(Modal.Content, {
      children: jsxs(DeleteTextWrapper, {
        "data-testid": "delete-preset-popup-content",
        children: [jsx("div", {
          children: "You are about to delete"
        }), jsxs("div", {
          children: ['"', activePresetForContextMenu.name, '" RNA preset.']
        }), jsx("div", {
          children: "This operation cannot be undone."
        })]
      })
    }), jsxs(Modal.Footer, {
      children: [jsx(StyledActionButton, {
        clickHandler: cancelHandler,
        label: "Cancel",
        styleType: "secondary",
        "data-testid": "cancel-delete-preset-button"
      }, "cancel"), jsx(StyledActionButton, {
        clickHandler: deleteHandler,
        label: "Delete",
        "data-testid": "delete-preset-button"
      }, "delete")]
    })]
  });
};
var TextWrapper = createStyled("div", {
  target: "e1wvbgsi0"
} )({
  name: "606i4c",
  styles: "padding:12px"
} );
var UpdateSequenceInRNABuilder = function UpdateSequenceInRNABuilder2(_ref3) {
  var isModalOpen = _ref3.isModalOpen, onClose = _ref3.onClose;
  var dispatch2 = useAppDispatch();
  var sequenceSelection = useAppSelector(selectSequenceSelection);
  var editor = useAppSelector(selectEditor);
  var countOfNucleoelements = getCountOfNucleoelements(sequenceSelection);
  var onCloseCallback = reactExports.useCallback(function() {
    onClose();
  }, [onClose]);
  var reset = function reset2() {
    resetRnaBuilderAfterSequenceUpdate(dispatch2, editor);
  };
  var cancelHandler = function cancelHandler2() {
    onCloseCallback();
  };
  var updateHandler = function updateHandler2() {
    onCloseCallback();
    editor === null || editor === void 0 || editor.events.modifySequenceInRnaBuilder.dispatch(sequenceSelection);
    reset();
  };
  return jsxs(Modal, {
    isOpen: isModalOpen,
    title: "Update sequence",
    onClose: onCloseCallback,
    "data-testid": "update-sequence-modal",
    children: [jsx(Modal.Content, {
      "data-testid": "update-sequence-modal-body",
      children: jsxs(TextWrapper, {
        children: ["You are going to modify ", countOfNucleoelements, " nucleotides. Are you sure?"]
      })
    }), jsxs(Modal.Footer, {
      children: [jsx(ActionButton, {
        clickHandler: cancelHandler,
        label: "Cancel",
        styleType: "secondary",
        title: "",
        "data-testid": "update-sequence-cancel-button"
      }, "cancel"), jsx(ActionButton, {
        clickHandler: updateHandler,
        label: "Yes",
        title: "",
        "data-testid": "update-sequence-yes-button"
      }, "update")]
    })]
  });
};
var AttachmentPoint$2 = createStyled("div", {
  target: "e1tvvbc92"
} )(function() {
  return {
    display: "flex",
    flexDirection: "column",
    rowGap: "2px",
    alignItems: "center",
    marginBottom: "5px"
  };
}, "" );
var AttachmentPointName$1 = createStyled("span", {
  target: "e1tvvbc91"
} )(function(props) {
  return {
    margin: 0,
    padding: 0,
    textAlign: "center",
    display: "block",
    font: props.theme.ketcher.font.family.inter,
    fontSize: props.theme.ketcher.font.size.small,
    fontWeight: props.theme.ketcher.font.weight.regular,
    color: props.disabled ? "rgba(180, 185, 214, 1)" : props.theme.ketcher.color.text.light
  };
}, "" );
var ModalContent = createStyled("div", {
  target: "e1tvvbc90"
} )(function() {
  return {
    height: "100%"
  };
}, "" );
var hydrateLeavingGroup = function hydrateLeavingGroup2(leavingGroup) {
  return leavingGroup === "O" ? "OH" : leavingGroup;
};
var hydrateLeavingGroup$1 = hydrateLeavingGroup;
var StyledStructRender$1 = createStyled(StructRender, {
  target: "e1huhxto1"
} )(function(_ref3) {
  var theme = _ref3.theme, isExpanded = _ref3.isExpanded;
  return {
    display: "flex",
    border: "1.5px solid ".concat(theme.ketcher.outline.color),
    borderRadius: "6px",
    padding: 5,
    maxHeight: "100%",
    minHeight: "150px",
    height: isExpanded ? "auto" : "150px",
    width: isExpanded ? "auto" : "150px",
    alignSelf: "stretch",
    "& svg": {
      maxWidth: "fit-content",
      margin: "auto"
    }
  };
}, "" );
var AttachmentPointList = createStyled("div", {
  target: "e1huhxto0"
} )({
  name: "wfzm1y",
  styles: "display:flex;flex-wrap:wrap;justify-content:center;align-self:flex-start;width:100%;gap:7px"
} );
var StyledContent = createStyled("div", {
  target: "e8i5wzj0"
} )({
  name: "2oefzz",
  styles: "display:flex;flex-direction:column;justify-content:center;align-items:center;gap:8px;padding:8px;color:#7c7c7f;border:1px solid #cad3dd;width:100%;height:100%"
} );
var UnresolvedMonomerPreview = function UnresolvedMonomerPreview2(_ref3) {
  var testId = _ref3.testId;
  return jsxs(StyledContent, {
    "data-testid": testId,
    children: [jsx(Icon, {
      name: "questionMark"
    }), "Unknown structure"]
  });
};
var UnresolvedMonomerPreview$1 = UnresolvedMonomerPreview;
var Container$2 = createStyled("div", {
  target: "e1q9gayd0"
} )(function(_ref3) {
  var theme = _ref3.theme, expanded = _ref3.expanded;
  return {
    display: "flex",
    border: "1.5px solid ".concat(theme.ketcher.outline.color),
    borderRadius: "6px",
    padding: 5,
    maxHeight: "100%",
    minHeight: "150px",
    height: expanded ? "auto" : "150px",
    width: expanded ? "auto" : "150px",
    alignSelf: "stretch",
    "& svg": {
      maxWidth: "fit-content",
      margin: "auto"
    }
  };
}, "" );
var MonomerMiniature = function MonomerMiniature2(_ref3) {
  var monomer = _ref3.monomer, expanded = _ref3.expanded, selectedAttachmentPoint = _ref3.selectedAttachmentPoint, connectedAttachmentPoints = _ref3.connectedAttachmentPoints, usage = _ref3.usage, testId = _ref3.testId;
  var svgRef = reactExports.useRef(null);
  reactExports.useLayoutEffect(function() {
    var svg = svgRef.current;
    if (svg) {
      var svgElement = select(svg);
      if (monomer instanceof AmbiguousMonomer) {
        var centerX = (svg.width.baseVal.value - svg.x.baseVal.value) / 2;
        var centerY = (svg.height.baseVal.value - svg.y.baseVal.value) / 2;
        var position = new Vec2(centerX, centerY);
        var positionInAngstrom = Coordinates.canvasToModel(position);
        var variantMonomer = new AmbiguousMonomer(monomer.variantMonomerItem, positionInAngstrom);
        var renderer = new AmbiguousMonomerRenderer(variantMonomer);
        renderer.showExternal({
          canvas: svgElement,
          usage,
          selectedAttachmentPoint,
          connectedAttachmentPoints
        });
      }
    }
  }, [selectedAttachmentPoint, connectedAttachmentPoints]);
  return jsx(Container$2, {
    expanded,
    "data-testid": testId,
    children: jsx("svg", {
      ref: svgRef
    })
  });
};
var MonomerMiniature$1 = MonomerMiniature;
var MonomerOverview = function MonomerOverview2(_ref3) {
  var monomer = _ref3.monomer, attachmentPoints = _ref3.attachmentPoints, connectedAttachmentPoints = _ref3.connectedAttachmentPoints, selectedAttachmentPoint = _ref3.selectedAttachmentPoint, usage = _ref3.usage, needCache = _ref3.needCache, update = _ref3.update, expanded = _ref3.expanded, testId = _ref3.testId;
  var isAmbiguousMonomer = monomer instanceof AmbiguousMonomer;
  var isUnresolvedMonomer = monomer.monomerItem.props.unresolved;
  var monomerPreviewContent;
  if (isAmbiguousMonomer) {
    monomerPreviewContent = jsx(MonomerMiniature$1, {
      monomer,
      expanded,
      selectedAttachmentPoint,
      connectedAttachmentPoints,
      usage,
      testId
    });
  } else if (isUnresolvedMonomer) {
    monomerPreviewContent = jsx(UnresolvedMonomerPreview$1, {
      testId
    });
  } else {
    monomerPreviewContent = jsx(StyledStructRender$1, {
      struct: monomer.monomerItem.struct,
      options: {
        connectedMonomerAttachmentPoints: connectedAttachmentPoints,
        currentlySelectedMonomerAttachmentPoint: selectedAttachmentPoint !== null && selectedAttachmentPoint !== void 0 ? selectedAttachmentPoint : void 0,
        usageInMacromolecule: usage,
        labelInMonomerConnectionsModal: true,
        needCache: needCache !== null && needCache !== void 0 ? needCache : false
      },
      update,
      isExpanded: expanded,
      testId
    });
  }
  return jsxs(Fragment, {
    children: [monomerPreviewContent, jsx(AttachmentPointList, {
      children: jsx(Fragment, {
        children: attachmentPoints
      })
    })]
  });
};
var MonomerOverview$1 = MonomerOverview;
var MonomerName$1 = createStyled("div", {
  target: "e14t14ao2"
} )(function(_ref3) {
  var theme = _ref3.theme, isExpanded = _ref3.isExpanded;
  return {
    margin: 0,
    padding: 0,
    textAlign: "center",
    alignSelf: "flex-end",
    display: "block",
    font: theme.ketcher.font.family.inter,
    fontSize: theme.ketcher.font.size.regular,
    fontWeight: theme.ketcher.font.weight.regular,
    flexBasis: "200px",
    lineHeight: "14px",
    maxWidth: isExpanded ? void 0 : "150px"
  };
}, "" );
var ConnectionSymbol = createStyled("div", {
  target: "e14t14ao1"
} )(function(_ref22) {
  var theme = _ref22.theme;
  return {
    width: 10,
    height: 2,
    display: "block",
    color: theme.ketcher.color.button.secondary.hover,
    backgroundColor: theme.ketcher.color.button.secondary.hover,
    borderRadius: 20,
    margin: "auto"
  };
}, "" );
var AttachmentPointsRow = createStyled("div", {
  target: "e14t14ao0"
} )(function() {
  return {
    display: "grid",
    gridAutoFlow: "column",
    gridTemplateRows: "auto auto auto",
    gridTemplateColumns: "1fr 10px 1fr",
    justifyContent: "center",
    alignItems: "flex-start",
    padding: "12px",
    paddingBottom: 0,
    height: "100%",
    columnGap: "12px",
    rowGap: "8px"
  };
}, "" );
var DNA_TEMPLATE_NAME_PART = "thymine";
var RNA_TEMPLATE_NAME_PART = "uracil";
var getAmbiguousMonomerName = function getAmbiguousMonomerName2(monomer) {
  var _variantMonomerItem$o;
  var monomerClass = monomer.monomerClass, variantMonomerItem = monomer.variantMonomerItem;
  var label = variantMonomerItem.label;
  var options2 = (_variantMonomerItem$o = variantMonomerItem.options) !== null && _variantMonomerItem$o !== void 0 ? _variantMonomerItem$o : [];
  if (monomerClass === KetMonomerClass.Base) {
    var isDNA = options2.some(function(option) {
      return option.templateId.toLowerCase().includes(DNA_TEMPLATE_NAME_PART);
    });
    var isRNA = options2.some(function(option) {
      return option.templateId.toLowerCase().includes(RNA_TEMPLATE_NAME_PART);
    });
    if (isDNA) {
      return label === "N" ? "Any DNA base" : "Ambiguous DNA Base";
    }
    if (isRNA) {
      return label === "N" ? "Any RNA Base" : "Ambiguous RNA Base";
    }
    return "Ambiguous Base";
  }
  if (monomerClass === KetMonomerClass.AminoAcid) {
    return label === "X" ? "Any Amino acid" : "Ambiguous Amino acid";
  }
  return "Ambiguous ".concat(monomerClass);
};
var getMonomerName = function getMonomerName2(monomer) {
  if (monomer instanceof AmbiguousMonomer) {
    return getAmbiguousMonomerName(monomer);
  }
  return monomer.monomerItem.props.Name;
};
var getMonomerName$1 = getMonomerName;
var ConnectionOverview = function ConnectionOverview2(_ref3) {
  var firstMonomer = _ref3.firstMonomer, secondMonomer = _ref3.secondMonomer, expanded = _ref3.expanded, firstMonomerOverview = _ref3.firstMonomerOverview, secondMonomerOverview = _ref3.secondMonomerOverview;
  var firstMonomerName = getMonomerName$1(firstMonomer);
  var secondMonomerName = getMonomerName$1(secondMonomer);
  return jsx(AttachmentPointsRow, {
    children: jsxs(Fragment, {
      children: [jsx(MonomerName$1, {
        isExpanded: expanded,
        children: firstMonomerName
      }), firstMonomerOverview, jsx("span", {}), jsx(ConnectionSymbol, {}), jsx("span", {}), jsx(MonomerName$1, {
        isExpanded: expanded,
        children: secondMonomerName
      }), secondMonomerOverview]
    })
  });
};
var ConnectionOverview$1 = ConnectionOverview;
function ownKeys$8(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$8(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$8(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$8(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var StyledModal = createStyled(Modal, {
  target: "e1byht5d3"
} )({
  name: "1j7jcep",
  styles: "& .MuiPaper-root{background:#fff !important;}& .MuiDialogContent-root{overflow:hidden;}"
} );
var ActionButtonLeft = createStyled(ActionButton, {
  target: "e1byht5d2"
} )(function() {
  return {
    width: "97px !important"
  };
}, "" );
var ActionButtonRight = createStyled(ActionButton, {
  target: "e1byht5d1"
} )(function(props) {
  return {
    width: "97px !important",
    color: props.disabled ? "rgba(51, 51, 51, 0.6)" : "",
    background: props.disabled ? "rgba(225, 229, 234, 1) !important" : "",
    opacity: "1 !important",
    minHeight: "0"
  };
}, "" );
var ActionButtonAttachmentPoint = createStyled(ActionButton, {
  target: "e1byht5d0"
} )(function(props) {
  return {
    borderRadius: 5,
    minWidth: "45px !important",
    padding: "4px",
    border: "1px solid ".concat(props.theme.ketcher.color.border.secondary),
    color: props.disabled ? "rgba(51, 51, 51, 0.6) !important" : "",
    background: props.disabled ? "rgba(225, 229, 234)" : "",
    borderColor: props.disabled ? "rgba(225, 229, 234) !important" : ""
  };
}, "" );
var MonomerConnection = function MonomerConnection2(_ref3) {
  var onClose = _ref3.onClose, isModalOpen = _ref3.isModalOpen, firstMonomer = _ref3.firstMonomer, secondMonomer = _ref3.secondMonomer, polymerBond = _ref3.polymerBond, isReconnectionDialog = _ref3.isReconnectionDialog;
  var editor = useAppSelector(selectEditor);
  var initialFirstMonomerAttachmentPointRef = reactExports.useRef(polymerBond === null || polymerBond === void 0 ? void 0 : polymerBond.firstMonomerAttachmentPoint);
  var initialSecondMonomerAttachmentPointRef = reactExports.useRef(polymerBond === null || polymerBond === void 0 ? void 0 : polymerBond.secondMonomerAttachmentPoint);
  var hasFreeAttachmentPointsRef = reactExports.useRef((firstMonomer === null || firstMonomer === void 0 ? void 0 : firstMonomer.hasFreeAttachmentPoint) || (secondMonomer === null || secondMonomer === void 0 ? void 0 : secondMonomer.hasFreeAttachmentPoint));
  if (!firstMonomer || !secondMonomer) {
    throw new Error("Monomers must exist!");
  }
  var _useState = reactExports.useState(initialFirstMonomerAttachmentPointRef.current || getDefaultAttachmentPoint(firstMonomer)), _useState2 = _slicedToArray(_useState, 2), firstSelectedAttachmentPoint = _useState2[0], setFirstSelectedAttachmentPoint = _useState2[1];
  var _useState3 = reactExports.useState(initialSecondMonomerAttachmentPointRef.current || getDefaultAttachmentPoint(secondMonomer)), _useState4 = _slicedToArray(_useState3, 2), secondSelectedAttachmentPoint = _useState4[0], setSecondSelectedAttachmentPoint = _useState4[1];
  var _useState5 = reactExports.useState(false), _useState6 = _slicedToArray(_useState5, 2), modalExpanded = _useState6[0], setModalExpanded = _useState6[1];
  var cancelBondCreationAndClose = function cancelBondCreationAndClose2() {
    if (isReconnectionDialog) {
      var _polymerBond$secondMo;
      polymerBond === null || polymerBond === void 0 || polymerBond.firstMonomer.setBond(initialFirstMonomerAttachmentPointRef.current, polymerBond);
      polymerBond === null || polymerBond === void 0 || (_polymerBond$secondMo = polymerBond.secondMonomer) === null || _polymerBond$secondMo === void 0 || _polymerBond$secondMo.setBond(initialSecondMonomerAttachmentPointRef.current, polymerBond);
      onClose();
    } else {
      editor === null || editor === void 0 || editor.events.cancelBondCreationViaModal.dispatch(secondMonomer);
      onClose();
    }
  };
  var connectMonomers = function connectMonomers2() {
    if (!firstSelectedAttachmentPoint || !secondSelectedAttachmentPoint) {
      throw new Error("Attachment points cannot be falsy");
    }
    if (firstSelectedAttachmentPoint === initialFirstMonomerAttachmentPointRef.current && secondSelectedAttachmentPoint === initialSecondMonomerAttachmentPointRef.current) {
      cancelBondCreationAndClose();
      return;
    }
    editor === null || editor === void 0 || editor.events.createBondViaModal.dispatch({
      firstMonomer,
      secondMonomer,
      firstSelectedAttachmentPoint,
      secondSelectedAttachmentPoint,
      polymerBond,
      isReconnection: isReconnectionDialog,
      initialFirstMonomerAttachmentPoint: initialFirstMonomerAttachmentPointRef.current,
      initialSecondMonomerAttachmentPoint: initialSecondMonomerAttachmentPointRef.current
    });
    onClose();
  };
  return jsxs(StyledModal, {
    title: isReconnectionDialog ? "Edit Attachment Points" : "Select Attachment Points",
    isOpen: isModalOpen,
    onClose: cancelBondCreationAndClose,
    showExpandButton: true,
    modalWidth: "358px",
    expanded: modalExpanded,
    setExpanded: setModalExpanded,
    testId: "monomer-connection-modal",
    children: [jsx(Modal.Content, {
      children: jsx(ModalContent, {
        children: jsx(ConnectionOverview$1, {
          firstMonomer,
          secondMonomer,
          expanded: modalExpanded,
          firstMonomerOverview: jsx(AttachmentPointSelectionPanel, {
            monomer: firstMonomer,
            selectedAttachmentPoint: firstSelectedAttachmentPoint,
            onSelectAttachmentPoint: setFirstSelectedAttachmentPoint,
            expanded: modalExpanded,
            position: "left"
          }),
          secondMonomerOverview: jsx(AttachmentPointSelectionPanel, {
            monomer: secondMonomer,
            selectedAttachmentPoint: secondSelectedAttachmentPoint,
            onSelectAttachmentPoint: setSecondSelectedAttachmentPoint,
            expanded: modalExpanded,
            position: "right"
          })
        })
      })
    }), jsxs(Modal.Footer, {
      children: [jsx(ActionButtonLeft, {
        label: "Cancel",
        "data-testid": "cancel-button",
        styleType: "secondary",
        clickHandler: cancelBondCreationAndClose
      }), jsx(ActionButtonRight, {
        label: isReconnectionDialog ? "Reconnect" : "Connect",
        "data-testid": isReconnectionDialog ? "Reconnect-button" : "Connect-button",
        disabled: !firstSelectedAttachmentPoint || !secondSelectedAttachmentPoint || !hasFreeAttachmentPointsRef.current,
        clickHandler: connectMonomers
      })]
    })]
  });
};
function AttachmentPointSelectionPanel(_ref22) {
  var monomer = _ref22.monomer, selectedAttachmentPoint = _ref22.selectedAttachmentPoint, onSelectAttachmentPoint = _ref22.onSelectAttachmentPoint, _ref2$expanded = _ref22.expanded, expanded = _ref2$expanded === void 0 ? false : _ref2$expanded, position = _ref22.position;
  var _useState7 = reactExports.useState(monomer.attachmentPointsToBonds), _useState8 = _slicedToArray(_useState7, 2), bonds = _useState8[0], setBonds = _useState8[1];
  var _useState9 = reactExports.useState(function() {
    return getConnectedAttachmentPoints(bonds);
  }), _useState0 = _slicedToArray(_useState9, 2), connectedAttachmentPoints = _useState0[0], setConnectedAttachmentPoints = _useState0[1];
  reactExports.useEffect(function() {
    setBonds(monomer.attachmentPointsToBonds);
  }, [selectedAttachmentPoint]);
  reactExports.useEffect(function() {
    var newConnectedAttachmentPoints = getConnectedAttachmentPoints(bonds);
    setConnectedAttachmentPoints(newConnectedAttachmentPoints);
  }, [bonds]);
  var getLeavingGroup = function getLeavingGroup2(attachmentPoint) {
    var MonomerCaps = monomer.monomerCaps;
    var isAmbiguousMonomer = monomer instanceof AmbiguousMonomer;
    if (!MonomerCaps) {
      return isAmbiguousMonomer ? null : "H";
    }
    var leavingGroup = MonomerCaps[attachmentPoint];
    return hydrateLeavingGroup$1(leavingGroup);
  };
  var handleSelectAttachmentPoint = function handleSelectAttachmentPoint2(attachmentPoint) {
    var newBonds = _objectSpread$8({}, monomer.attachmentPointsToBonds);
    var selectedBond = selectedAttachmentPoint ? newBonds[selectedAttachmentPoint] : null;
    if (selectedAttachmentPoint && selectedBond) {
      monomer.removeBond(selectedBond);
    }
    var potentialBond = monomer.getPotentialBond(attachmentPoint);
    newBonds[attachmentPoint] = potentialBond;
    setBonds(newBonds);
    onSelectAttachmentPoint(attachmentPoint);
    var newConnectedAttachmentPoints = getConnectedAttachmentPoints(newBonds);
    setConnectedAttachmentPoints(newConnectedAttachmentPoints);
  };
  return jsx(MonomerOverview$1, {
    monomer,
    connectedAttachmentPoints,
    selectedAttachmentPoint,
    usage: UsageInMacromolecule.MonomerConnectionsModal,
    update: expanded,
    expanded,
    attachmentPoints: monomer.listOfAttachmentPoints.map(function(attachmentPoint) {
      var disabled = Boolean(connectedAttachmentPoints.includes(attachmentPoint) && attachmentPoint !== selectedAttachmentPoint);
      return jsxs(AttachmentPoint$2, {
        children: [jsx(ActionButtonAttachmentPoint, {
          label: attachmentPoint,
          styleType: attachmentPoint === selectedAttachmentPoint ? "primary" : "secondary",
          clickHandler: function clickHandler() {
            return handleSelectAttachmentPoint(attachmentPoint);
          },
          disabled,
          "data-testid": "".concat(position, "-").concat(attachmentPoint),
          "data-isactive": attachmentPoint === selectedAttachmentPoint
        }), jsx(AttachmentPointName$1, {
          "data-testid": "leaving-group-value",
          disabled,
          children: getLeavingGroup(attachmentPoint)
        })]
      }, attachmentPoint);
    }),
    testId: "".concat(position, "-monomer-preview")
  });
}
function getDefaultAttachmentPoint(monomer) {
  if (monomer.chosenFirstAttachmentPointForBond) return monomer.chosenFirstAttachmentPointForBond;
  if (monomer.chosenSecondAttachmentPointForBond) return monomer.chosenSecondAttachmentPointForBond;
  var possibleAttachmentPoints = Object.entries(monomer.attachmentPointsToBonds).filter(function(_ref3) {
    var _ref4 = _slicedToArray(_ref3, 2);
    _ref4[0];
    var bond = _ref4[1];
    return bond == null;
  });
  if (possibleAttachmentPoints.length === 1) {
    var _possibleAttachmentPo = _slicedToArray(possibleAttachmentPoints[0], 1), attachmentPointName = _possibleAttachmentPo[0];
    return attachmentPointName;
  }
  return null;
}
var ConfirmationText = createStyled("p", {
  target: "e1e4h5hm0"
} )({
  name: "1fayh9l",
  styles: "padding:12px;font-size:12px;color:#000"
} );
var ConfirmationDialog = function ConfirmationDialog2(_ref3) {
  var title = _ref3.title, confirmationText = _ref3.confirmationText, onConfirm = _ref3.onConfirm, isModalOpen = _ref3.isModalOpen, onClose = _ref3.onClose;
  var handleConfirm = function handleConfirm2() {
    onConfirm();
    onClose();
  };
  return jsxs(Modal, {
    isOpen: isModalOpen,
    title: title !== null && title !== void 0 ? title : "Confirm your action",
    onClose,
    testId: "confirmation-dialog",
    children: [jsx(Modal.Content, {
      children: jsx(ConfirmationText, {
        "data-testid": "confirmation-text",
        children: confirmationText
      })
    }), jsxs(Modal.Footer, {
      children: [jsx(ActionButton, {
        label: "Cancel",
        clickHandler: onClose,
        "data-testid": "cancel-button"
      }), jsx(ActionButton, {
        label: "Yes",
        clickHandler: handleConfirm,
        styleType: "secondary",
        "data-testid": "yes-button"
      })]
    })]
  });
};
var modalComponentList = {
  open: Open,
  save: Save,
  "delete": Delete,
  updateSequenceInRNABuilder: UpdateSequenceInRNABuilder,
  monomerConnection: MonomerConnection,
  confirmationDialog: ConfirmationDialog
};
function ownKeys$7(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$7(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$7(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$7(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var ModalContainer = function ModalContainer2() {
  var isOpen = useAppSelector(selectModalIsOpen);
  var modalName = useAppSelector(selectModalName);
  var additionalProps = useAppSelector(selectAdditionalProps);
  var dispatch2 = useAppDispatch();
  var handleClose = reactExports.useCallback(function() {
    dispatch2(closeModal2());
  }, [dispatch2]);
  if (!modalName) return null;
  var Component = modalComponentList[modalName];
  if (!Component) throw new Error("There is no modal window named ".concat(modalName));
  return additionalProps ? jsx(Component, _objectSpread$7({
    onClose: handleClose,
    isModalOpen: isOpen
  }, additionalProps)) : jsx(Component, {
    onClose: handleClose,
    isModalOpen: isOpen
  });
};
var StyledToastContainer = createStyled("div", {
  target: "e15avtnm3"
} )({
  name: "3w0yoi",
  styles: "display:flex;flex-direction:column;gap:8px"
} );
var StyledToast = createStyled("div", {
  target: "e15avtnm2"
} )({
  name: "1bweptz",
  styles: "background-color:#333333;max-height:40px;display:flex;align-items:stretch"
} );
var StyledToastContent = createStyled("div", {
  target: "e15avtnm1"
} )({
  name: "1my6l07",
  styles: "max-width:356px;padding:4px 10px 4px 10px;color:white;display:flex"
} );
var StyledIconButton$1 = createStyled(IconButton, {
  target: "e15avtnm0"
} )({
  name: "1c8hqv0",
  styles: "color:white;width:24px;height:auto;display:flex;align-items:center;justify-content:center;&:hover{background-color:#585858;color:white;}svg{width:16px;height:16px;}"
} );
var ChemAvatar = function ChemAvatar2() {
  return jsxs(Fragment, {
    children: [jsx("symbol", {
      id: "chem",
      viewBox: "0 0 59 59",
      width: "59",
      height: "59",
      children: jsx("rect", {
        className: "monomer-body",
        width: "29.5",
        height: "29.5",
        "data-actual-width": "29.5",
        "data-actual-height": "29.5",
        x: "0.5",
        y: "0.5",
        rx: "0.75"
      })
    }), jsx("symbol", {
      id: "chem-selection",
      viewBox: "0 0 59 59",
      width: "59",
      height: "59",
      children: jsx("rect", {
        width: "29.5",
        height: "29.5",
        x: "0.5",
        y: "0.5",
        rx: "0.75",
        stroke: "#0097A8",
        fill: "none",
        strokeWidth: "1.5"
      })
    }), jsxs("symbol", {
      id: "chem-autochain-preview",
      viewBox: "0 0 32 32",
      width: "32",
      height: "32",
      "data-actual-width": "32",
      "data-actual-height": "32",
      children: [jsx("path", {
        d: "M1 4.63574V2.63574C1 1.53117 1.89543 0.635742 3 0.635742H5"
      }), jsx("path", {
        d: "M1 26.6357V28.6357C1 29.7403 1.89543 30.6357 3 30.6357H5"
      }), jsx("path", {
        d: "M31 4.63574V2.63574C31 1.53117 30.1046 0.635742 29 0.635742H27"
      }), jsx("path", {
        d: "M31 26.6357V28.6357C31 29.7403 30.1046 30.6357 29 30.6357H27"
      }), jsx("path", {
        d: "M7.02142 30.6357L10.0214 30.6357"
      }), jsx("path", {
        d: "M12.0013 30.6357L15.0013 30.6357"
      }), jsx("path", {
        d: "M16.9816 30.6357L19.9816 30.6357"
      }), jsx("path", {
        d: "M22.0222 30.6357L25.0222 30.6357"
      }), jsx("path", {
        d: "M1.02185 6.63574L1.02185 9.63574"
      }), jsx("path", {
        d: "M1.02185 11.6152L1.02185 14.6152"
      }), jsx("path", {
        d: "M1.02185 16.5957L1.02185 19.5957"
      }), jsx("path", {
        d: "M1.02185 21.6367L1.02185 24.6367"
      }), jsx("path", {
        d: "M7.02142 0.635742L10.0214 0.635742"
      }), jsx("path", {
        d: "M12.0013 0.635742L15.0013 0.635742"
      }), jsx("path", {
        d: "M16.9816 0.635742L19.9816 0.635742"
      }), jsx("path", {
        d: "M22.0222 0.635742L25.0222 0.635742"
      }), jsx("path", {
        d: "M31.0219 6.63574L31.0219 9.63574"
      }), jsx("path", {
        d: "M31.0219 11.6152L31.0219 14.6152"
      }), jsx("path", {
        d: "M31.0219 16.5957L31.0219 19.5957"
      }), jsx("path", {
        d: "M31.0219 21.6367L31.0219 24.6367"
      })]
    })]
  });
};
var PeptideAvatar = function PeptideAvatar2() {
  return jsxs(Fragment, {
    children: [jsx("symbol", {
      id: "peptide",
      viewBox: "0 0 70 61",
      width: "70",
      height: "61",
      children: jsx("path", {
        className: "monomer-body",
        transform: "scale(0.5)",
        "data-actual-width": "35",
        "data-actual-height": "30.5",
        d: "M16.9236 1.00466C17.2801 0.383231 17.9418 6.10888e-07 18.6583 5.98224e-07L51.3417 2.04752e-08C52.0582 7.81036e-09 52.7199 0.383234 53.0764 1.00466L69.4289 29.5047C69.7826 30.1211 69.7826 30.8789 69.4289 31.4953L53.0764 59.9953C52.7199 60.6168 52.0582 61 51.3417 61H18.6583C17.9418 61 17.2801 60.6168 16.9236 59.9953L0.571095 31.4953C0.217407 30.8789 0.217408 30.1211 0.571096 29.5047L16.9236 1.00466Z"
      })
    }), jsxs("symbol", {
      id: "peptide-hover",
      viewBox: "0 0 70 61",
      width: "70",
      height: "61",
      children: [jsx("path", {
        d: "M18.2246 1.75116C18.3137 1.59581 18.4792 1.5 18.6583 1.5L51.3417 1.5C51.5208 1.5 51.6863 1.59581 51.7754 1.75116L53.06 1.01408L51.7754 1.75117L68.1279 30.2512C68.2163 30.4053 68.2163 30.5947 68.1279 30.7488L51.7754 59.2488C51.6863 59.4042 51.5208 59.5 51.3417 59.5H18.6583C18.4792 59.5 18.3137 59.4042 18.2246 59.2488L1.87215 30.7488C1.78372 30.5947 1.78372 30.4053 1.87215 30.2512L18.2246 1.75116Z",
        fill: "none",
        transform: "scale(0.5)",
        stroke: "#0097A8",
        strokeWidth: "3"
      }), " "]
    }), jsx("symbol", {
      id: "modified-background",
      viewBox: "0 0 60 20",
      width: "30",
      height: "20",
      x: "2.5",
      y: "5",
      children: jsx("path", {
        xmlns: "http://www.w3.org/2000/svg",
        d: "M6.52702 20C5.81057 20 5.14885 19.6168 4.79229 18.9953L0.570974 11.6382C0.217285 11.0218 \n           0.217285 10.2639 0.570974 9.64751L5.52999 1.00466C5.88654 0.383235 6.54827 0 7.26472 0H52.735C53.4515\n           0 54.1132 0.383234 54.4698 1.00466L59.4288 9.64751C59.7825 10.2639 59.7825 11.0218 59.4288 11.6382\n           L55.2075 18.9953C54.8509 19.6168 54.1892 20 53.4727 20H6.52702Z",
        fillOpacity: "0.6"
      })
    }), jsxs("symbol", {
      id: "peptide-autochain-preview",
      viewBox: "0 0 37 32",
      width: "37",
      height: "32",
      "data-actual-width": "37",
      "data-actual-height": "32",
      children: [jsx("path", {
        d: "M8.27143 3.53027L9.29272 1.77462C9.65083 1.15901 10.3093 0.780274 11.0215 0.780274L13.1642 0.780274M29.2131 3.53027L28.1919 1.77462C27.8337 1.15901 27.1753 0.780273 26.4631 0.780273L24.3164 0.780273M2.45429 13.5303L1.585 15.0246C1.22337 15.6463 1.22337 16.4143 1.585 17.0359L2.45429 18.5303M29.0386 28.5303L28.0233 30.2756C27.6619 30.897 26.991 31.2803 26.2646 31.2803L24.1459 31.2803M8.09693 28.5303L9.11221 30.2756C9.47371 30.897 10.1446 31.2803 10.871 31.2803H12.9936M34.8558 18.5303L35.7311 17.0256C36.0896 16.4092 36.0896 15.6514 35.7311 15.0349L34.8558 13.5303"
      }), jsx("path", {
        d: "M14.8937 0.780178L17.8937 0.780178"
      }), jsx("path", {
        d: "M19.597 0.780178L22.597 0.780178"
      }), jsx("path", {
        d: "M14.8937 31.2804H17.8937"
      }), jsx("path", {
        d: "M19.597 31.2804H22.597"
      }), jsx("path", {
        d: "M3.61253 11.7412L5.11253 9.14309"
      }), jsx("path", {
        d: "M5.96421 7.66792L7.46421 5.06984"
      }), jsx("path", {
        d: "M30.1034 26.877L31.6034 24.2789"
      }), jsx("path", {
        d: "M32.455 22.8038L33.955 20.2057"
      }), jsx("path", {
        d: "M7.32633 26.9903L5.82633 24.3922"
      }), jsx("path", {
        d: "M4.97465 22.917L3.47465 20.319"
      }), jsx("path", {
        d: "M33.9528 11.8759L32.4782 9.26339"
      }), jsx("path", {
        d: "M31.6409 7.78023L30.1662 5.16769"
      })]
    })]
  });
};
var SugarAvatar = function SugarAvatar2() {
  return jsxs(Fragment, {
    children: [jsx("symbol", {
      id: "sugar",
      viewBox: "0 0 70 70",
      width: "70",
      height: "70",
      children: jsx("rect", {
        className: "monomer-body",
        width: "28.5",
        height: "28.5",
        "data-actual-width": "28.5",
        "data-actual-height": "28.5",
        rx: "5"
      })
    }), jsx("symbol", {
      id: "sugar-selection",
      viewBox: "-1 -1 100 100",
      width: "70",
      height: "70",
      children: jsx("rect", {
        width: "39",
        height: "39",
        rx: "5",
        fill: "none",
        stroke: "#0097A8",
        strokeWidth: "2.5"
      })
    }), jsx("symbol", {
      id: "sugar-variant",
      viewBox: "0 0 72 72",
      width: "70",
      height: "70",
      children: jsx("rect", {
        className: "monomer-body",
        width: "28.5",
        height: "28.5",
        "data-actual-width": "28.5",
        "data-actual-height": "28.5",
        x: "0.5",
        y: "0.5",
        rx: "5",
        stroke: "#585858",
        strokeWidth: "0.5"
      })
    }), jsx("symbol", {
      id: "sugar-modified-background",
      viewBox: "0 0 28 10",
      width: "27",
      height: "10",
      x: "0.7",
      y: "10",
      children: jsx("path", {
        d: "M1.5 10C0.947715 10 0.5 9.55229 0.5 9V1C0.5 0.447715 0.947715 0 1.5 0H26.5C27.0523 0 27.5 0.447715 27.5 1V9C27.5 9.55228 27.0523 10 26.5 10H1.5Z",
        fill: "white",
        fillOpacity: "0.6"
      })
    }), jsxs("symbol", {
      id: "sugar-autochain-preview",
      viewBox: "0 0 32 32",
      width: "32",
      height: "32",
      "data-actual-width": "32",
      "data-actual-height": "32",
      children: [jsx("path", {
        d: "M1 4.63574V2.63574C1 1.53117 1.89543 0.635742 3 0.635742H5"
      }), jsx("path", {
        d: "M1 26.6357V28.6357C1 29.7403 1.89543 30.6357 3 30.6357H5"
      }), jsx("path", {
        d: "M31 4.63574V2.63574C31 1.53117 30.1046 0.635742 29 0.635742H27"
      }), jsx("path", {
        d: "M31 26.6357V28.6357C31 29.7403 30.1046 30.6357 29 30.6357H27"
      }), jsx("path", {
        d: "M7.02142 30.6357L10.0214 30.6357"
      }), jsx("path", {
        d: "M12.0013 30.6357L15.0013 30.6357"
      }), jsx("path", {
        d: "M16.9816 30.6357L19.9816 30.6357"
      }), jsx("path", {
        d: "M22.0222 30.6357L25.0222 30.6357"
      }), jsx("path", {
        d: "M1.02185 6.63574L1.02185 9.63574"
      }), jsx("path", {
        d: "M1.02185 11.6152L1.02185 14.6152"
      }), jsx("path", {
        d: "M1.02185 16.5957L1.02185 19.5957"
      }), jsx("path", {
        d: "M1.02185 21.6367L1.02185 24.6367"
      }), jsx("path", {
        d: "M7.02142 0.635742L10.0214 0.635742"
      }), jsx("path", {
        d: "M12.0013 0.635742L15.0013 0.635742"
      }), jsx("path", {
        d: "M16.9816 0.635742L19.9816 0.635742"
      }), jsx("path", {
        d: "M22.0222 0.635742L25.0222 0.635742"
      }), jsx("path", {
        d: "M31.0219 6.63574L31.0219 9.63574"
      }), jsx("path", {
        d: "M31.0219 11.6152L31.0219 14.6152"
      }), jsx("path", {
        d: "M31.0219 16.5957L31.0219 19.5957"
      }), jsx("path", {
        d: "M31.0219 21.6367L31.0219 24.6367"
      })]
    })]
  });
};
var PhosphateAvatar = function PhosphateAvatar2() {
  return jsxs(Fragment, {
    children: [jsx("symbol", {
      id: "phosphate",
      viewBox: "0 0 70 70",
      width: "70",
      height: "70",
      children: jsx("rect", {
        className: "monomer-body",
        width: "28",
        height: "28",
        "data-actual-width": "28",
        "data-actual-height": "28",
        rx: "15"
      })
    }), jsx("symbol", {
      id: "phosphate-selection",
      viewBox: "-1 -1 75 75",
      width: "70",
      height: "70",
      children: jsx("rect", {
        width: "28",
        height: "28",
        rx: "15",
        fill: "none",
        stroke: "#0097A8",
        strokeWidth: "1.5"
      })
    }), jsx("symbol", {
      id: "phosphate-variant",
      viewBox: "0 0 70 70",
      width: "70",
      height: "70",
      children: jsx("rect", {
        className: "monomer-body",
        width: "27",
        height: "27",
        "data-actual-width": "27",
        "data-actual-height": "27",
        stroke: "#585858",
        strokeWidth: "0.5",
        x: "0.5",
        y: "0.5",
        rx: "15"
      })
    }), jsx("symbol", {
      id: "phosphate-modified-background",
      viewBox: "0 0 28 10",
      width: "26",
      height: "10",
      x: "1",
      y: "9.5",
      children: jsx("path", {
        d: "M2.13388 0C1.72465 0 1.35333 0.248229 1.22109 0.635509C0.753639 2.00455 0.5 3.47265 0.5 5C0.5 6.52735 0.753639 7.99545 1.22109 9.36449C1.35333 9.75177 1.72465 10 2.13389 10H25.8661C26.2753 10 26.6467 9.75177 26.7789 9.36449C27.2464 7.99545 27.5 6.52735 27.5 5C27.5 3.47265 27.2464 2.00455 26.7789 0.635509C26.6467 0.248229 26.2753 0 25.8661 0H2.13388Z",
        fill: "#333333",
        fillOpacity: "0.6"
      })
    }), jsx("symbol", {
      id: "phosphate-autochain-preview",
      viewBox: "-1 -1 30 30",
      width: "30",
      height: "30",
      "data-actual-width": "30",
      "data-actual-height": "30",
      children: jsx("rect", {
        width: "28",
        height: "28",
        rx: "15",
        strokeDasharray: "4 4"
      })
    })]
  });
};
var RNABaseAvatar = function RNABaseAvatar2() {
  return jsxs(Fragment, {
    children: [jsx("symbol", {
      id: "rna-base",
      viewBox: "-16 0 65 65",
      width: "65",
      height: "95",
      children: jsx("rect", {
        width: "22.5",
        height: "22.5",
        "data-actual-width": "31.82",
        "data-actual-height": "31.82",
        rx: "1",
        x: "-11.25",
        y: "-11.25",
        transform: "rotate(45)",
        className: "monomer-body"
      })
    }), jsx("symbol", {
      id: "rna-base-selection",
      viewBox: "-15.75 -0.25 65 65",
      width: "65",
      height: "95",
      children: jsx("rect", {
        width: "21",
        height: "21",
        rx: "1",
        x: "-10.5",
        y: "-10.5",
        transform: "rotate(45)",
        stroke: "#0097A8",
        strokeWidth: "1.5",
        fill: "none"
      })
    }), jsx("symbol", {
      id: "rna-base-variant",
      viewBox: "-16 0 65 65",
      width: "65",
      height: "94",
      children: jsx("rect", {
        width: "21.5",
        height: "21.5",
        "data-actual-width": "30",
        "data-actual-height": "30",
        stroke: "#585858",
        strokeWidth: "0.5",
        rx: "1",
        x: "-10.25",
        y: "-10.25",
        transform: "rotate(45)",
        className: "monomer-body"
      })
    }), jsx("symbol", {
      id: "rna-base-modified-background",
      viewBox: "0 0 32 10",
      width: "30",
      height: "9",
      x: "0.8",
      y: "10.8",
      children: jsx("path", {
        fillRule: "evenodd",
        clipRule: "evenodd",
        d: "M6.30156 10C6.03634 10 5.78199 9.89464 5.59445 9.70711L1.1508 5.26346C0.760279 4.87293 0.760279 4.23977 1.1508 3.84924L4.70715 0.292893C4.89469 0.105357 5.14904 0 5.41426 0H26.5858C26.851 0 27.1054 0.105357 27.2929 0.292893L30.8493 3.84924C31.2398 4.23977 31.2398 4.87293 30.8493 5.26346L26.4056 9.70711C26.2181 9.89464 25.9637 10 25.6985 10H6.30156Z",
        fill: "#333333",
        fillOpacity: "0.6"
      })
    }), jsxs("symbol", {
      id: "rna-base-autochain-preview",
      viewBox: "0 0 36 36",
      width: "36",
      height: "36",
      "data-actual-width": "36",
      "data-actual-height": "36",
      children: [jsx("path", {
        d: "M2.77636 20.2837L1.83359 19.341C1.05254 18.5599 1.05254 17.2936 1.83359 16.5125L2.77468 15.5715"
      }), jsx("path", {
        d: "M15.7398 33.2465L16.6826 34.1893C17.4636 34.9704 18.73 34.9704 19.511 34.1893L20.4521 33.2482"
      }), jsx("path", {
        d: "M20.4412 2.61969L19.4984 1.67691C18.7173 0.89586 17.451 0.895861 16.67 1.67691L15.7289 2.618"
      }), jsx("path", {
        d: "M33.4046 15.5825L34.3474 16.5252C35.1284 17.3063 35.1284 18.5726 34.3474 19.3537L33.4063 20.2948"
      }), jsx("path", {
        d: "M21.6425 32.0586L23.4089 30.2921"
      }), jsx("path", {
        d: "M24.5747 29.126L26.3412 27.3595"
      }), jsx("path", {
        d: "M27.5073 26.1934L29.2737 24.4269"
      }), jsx("path", {
        d: "M30.4753 23.2256L32.2418 21.4591"
      }), jsx("path", {
        d: "M3.96771 21.4492L5.73546 23.217"
      }), jsx("path", {
        d: "M6.90216 24.3838L8.6699 26.1515"
      }), jsx("path", {
        d: "M9.83673 27.3184L11.6045 29.0861"
      }), jsx("path", {
        d: "M12.8069 30.2881L14.5747 32.0558"
      }), jsx("path", {
        d: "M3.96497 14.3809L5.73145 12.6144"
      }), jsx("path", {
        d: "M6.89728 11.4482L8.66376 9.68176"
      }), jsx("path", {
        d: "M9.82977 8.5166L11.5963 6.75012"
      }), jsx("path", {
        d: "M12.7979 5.54785L14.5643 3.78137"
      }), jsx("path", {
        d: "M21.6326 3.78418L23.4003 5.55192"
      }), jsx("path", {
        d: "M24.567 6.71875L26.3347 8.48649"
      }), jsx("path", {
        d: "M27.5016 9.65332L29.2693 11.4211"
      }), jsx("path", {
        d: "M30.4718 12.623L32.2395 14.3908"
      })]
    })]
  });
};
var UnresolvedMonomerAvatar = function UnresolvedMonomerAvatar2() {
  return jsxs(Fragment, {
    children: [jsxs("symbol", {
      id: "unresolved-monomer",
      viewBox: "0 0 59 59",
      width: "59",
      height: "59",
      children: [jsx("rect", {
        className: "monomer-body",
        width: "29.5",
        height: "29.5",
        "data-actual-width": "29.5",
        "data-actual-height": "29.5",
        x: "0.5",
        y: "0.5",
        rx: "1.5",
        stroke: "#333333"
      }), jsx("rect", {
        width: "29.5",
        height: "29.5",
        "data-actual-width": "29.5",
        "data-actual-height": "29.5",
        x: "0.5",
        y: "0.5",
        rx: "1.5",
        fill: "#585858"
      })]
    }), jsx("symbol", {
      id: "unresolved-monomer-hover",
      children: jsx("rect", {
        width: "29.5",
        height: "29.5",
        x: "0.5",
        y: "0.5",
        rx: "1.5",
        fill: "none",
        stroke: "#0097A8",
        strokeWidth: "1.5"
      })
    }), jsxs("symbol", {
      id: "unresolved-monomer-autochain-preview",
      viewBox: "0 0 32 32",
      width: "32",
      height: "32",
      "data-actual-width": "32",
      "data-actual-height": "32",
      children: [jsx("path", {
        d: "M1 4.63574V2.63574C1 1.53117 1.89543 0.635742 3 0.635742H5"
      }), jsx("path", {
        d: "M1 26.6357V28.6357C1 29.7403 1.89543 30.6357 3 30.6357H5"
      }), jsx("path", {
        d: "M31 4.63574V2.63574C31 1.53117 30.1046 0.635742 29 0.635742H27"
      }), jsx("path", {
        d: "M31 26.6357V28.6357C31 29.7403 30.1046 30.6357 29 30.6357H27"
      }), jsx("path", {
        d: "M7.02142 30.6357L10.0214 30.6357"
      }), jsx("path", {
        d: "M12.0013 30.6357L15.0013 30.6357"
      }), jsx("path", {
        d: "M16.9816 30.6357L19.9816 30.6357"
      }), jsx("path", {
        d: "M22.0222 30.6357L25.0222 30.6357"
      }), jsx("path", {
        d: "M1.02185 6.63574L1.02185 9.63574"
      }), jsx("path", {
        d: "M1.02185 11.6152L1.02185 14.6152"
      }), jsx("path", {
        d: "M1.02185 16.5957L1.02185 19.5957"
      }), jsx("path", {
        d: "M1.02185 21.6367L1.02185 24.6367"
      }), jsx("path", {
        d: "M7.02142 0.635742L10.0214 0.635742"
      }), jsx("path", {
        d: "M12.0013 0.635742L15.0013 0.635742"
      }), jsx("path", {
        d: "M16.9816 0.635742L19.9816 0.635742"
      }), jsx("path", {
        d: "M22.0222 0.635742L25.0222 0.635742"
      }), jsx("path", {
        d: "M31.0219 6.63574L31.0219 9.63574"
      }), jsx("path", {
        d: "M31.0219 11.6152L31.0219 14.6152"
      }), jsx("path", {
        d: "M31.0219 16.5957L31.0219 19.5957"
      }), jsx("path", {
        d: "M31.0219 21.6367L31.0219 24.6367"
      })]
    })]
  });
};
var NucleotideAvatar = function NucleotideAvatar2() {
  return jsxs(Fragment, {
    children: [jsx("symbol", {
      id: "nucleotide",
      viewBox: "0 0 84 84",
      width: "42",
      height: "42",
      children: jsx("path", {
        className: "monomer-body",
        "data-actual-width": "42",
        "data-actual-height": "42",
        d: "M43.0152 71.4019C42.3887 71.771 41.6113 71.771 40.9848 71.4019L9.25584 52.7093C8.50744 52.2684 8.1292 51.3948 8.31974 50.5473L16.6358 13.5613C16.841 12.6485 17.6516 12 18.5871 12L65.4129 12C66.3484 12 67.159 12.6485 67.3642 13.5613L75.6803 50.5473C75.8708 51.3948 75.4926 52.2684 74.7442 52.7093L43.0152 71.4019Z",
        transform: "rotate(180, 42, 42)"
      })
    }), jsx("symbol", {
      id: "nucleotide-hover",
      viewBox: "0 0 84 84",
      width: "42",
      height: "42",
      children: jsx("path", {
        "data-actual-width": "42",
        "data-actual-height": "42",
        d: "M43.0152 71.4019C42.3887 71.771 41.6113 71.771 40.9848 71.4019L9.25584 52.7093C8.50744 52.2684 8.1292 51.3948 8.31974 50.5473L16.6358 13.5613C16.841 12.6485 17.6516 12 18.5871 12L65.4129 12C66.3484 12 67.159 12.6485 67.3642 13.5613L75.6803 50.5473C75.8708 51.3948 75.4926 52.2684 74.7442 52.7093L43.0152 71.4019Z",
        transform: "rotate(180, 42, 42)",
        fill: "none",
        stroke: "#0097A8",
        strokeWidth: "3"
      })
    }), jsxs("symbol", {
      id: "nucleotide-autochain-preview",
      viewBox: "0 0 36 32",
      width: "36",
      height: "32",
      "data-actual-width": "36",
      "data-actual-height": "32",
      children: [jsx("path", {
        d: "M20.3771 2.38574L18.5929 1.0722C18.2402 0.812609 17.7598 0.812609 17.4071 1.0722L15.6229 2.38574M32.6021 11.3857L34.4405 12.7392C34.7769 12.9868 34.9239 13.4174 34.8092 13.8191L34.2725 15.6985M3.39787 11.3857L1.55948 12.7392C1.2231 12.9868 1.07608 13.4174 1.19078 13.8191L1.72751 15.6985M30.8088 27.8266L30.2138 29.9168C30.0914 30.3466 29.6988 30.643 29.252 30.643H27.0063M5.19116 27.8266L5.7931 29.9194C5.91633 30.3479 6.30831 30.643 6.75414 30.643H9.00194"
      }), jsx("path", {
        d: "M10.5017 30.6426L13.5017 30.6426"
      }), jsx("path", {
        d: "M16.5032 30.6426L19.5032 30.6426"
      }), jsx("path", {
        d: "M22.5046 30.6426L25.5046 30.6426"
      }), jsx("path", {
        d: "M2.23663 17.4971L3.06363 20.3808"
      }), jsx("path", {
        d: "M3.83911 23.0859L4.66611 25.9697"
      }), jsx("path", {
        d: "M22.356 3.85059L25.5765 6.22306"
      }), jsx("path", {
        d: "M27.5099 7.64746L30.7304 10.0199"
      }), jsx("path", {
        d: "M13.605 3.85156L10.3846 6.22404"
      }), jsx("path", {
        d: "M8.45105 7.64844L5.23059 10.0209"
      }), jsx("path", {
        d: "M33.7705 17.4971L32.9435 20.3808"
      }), jsx("path", {
        d: "M32.168 23.0859L31.341 25.9697"
      })]
    })]
  });
};
var ArrowMarker = function ArrowMarker2() {
  return jsxs(Fragment, {
    children: [jsx("path", {
      strokeLinecap: "round",
      d: "M5,0 0,2.5 5,5z",
      id: "arrow-marker-content"
    }), jsx("marker", {
      id: "arrow-marker",
      markerHeight: "3",
      markerWidth: "5",
      orient: "auto",
      refX: "2.5",
      refY: "1.5",
      children: jsx("use", {
        href: "#arrow-marker-content",
        transform: "rotate(180 2.5 1.5) scale(1,0.6)",
        strokeWidth: "1.2500",
        fill: "black",
        stroke: "none"
      })
    }), jsx("marker", {
      id: "arrow-marker-arc",
      markerWidth: "5",
      markerHeight: "5",
      viewBox: "0 0 5 5",
      refX: "5",
      refY: "2.5",
      orient: "auto",
      children: jsx("use", {
        href: "#arrow-marker-content",
        transform: "rotate(180, 2.5, 2.5)",
        fill: "#365CFF",
        stroke: "none"
      })
    })]
  });
};
var SequenceStartArrow = function SequenceStartArrow2() {
  return jsx("symbol", {
    id: "sequence-start-arrow",
    viewBox: "0 0 65 65",
    width: "65",
    height: "95",
    children: jsx("svg", {
      width: "12",
      height: "12",
      viewBox: "0 0 12 12",
      fill: "none",
      xmlns: "http://www.w3.org/2000/svg",
      children: jsx("path", {
        d: "M10.2802 5.09664C10.9756 5.49813 10.9756 6.50187 10.2802 6.90336L2.56467 11.3579C1.86926 11.7594 1 11.2576 1 10.4546V1.54541C1 0.742426 1.86926 0.240558 2.56467 0.642053L10.2802 5.09664Z",
        stroke: "#7C7C7F"
      })
    })
  });
};
var ErrorTextWrapper = createStyled("div", {
  target: "e1phidy70"
} )({
  name: "1fayh9l",
  styles: "padding:12px;font-size:12px;color:#000"
} );
var ErrorModal = function ErrorModal2() {
  var dispatch2 = useAppDispatch();
  var errorMessage = useAppSelector(selectErrorModalText);
  var errorTitle = useAppSelector(selectErrorModalTitle) || "Error message";
  var isModalOpen = errorMessage !== "";
  var onClose = function onClose2() {
    dispatch2(closeErrorModal2());
  };
  return jsxs(Modal, {
    isOpen: isModalOpen,
    title: errorTitle,
    onClose,
    testId: "info-modal-window",
    children: [jsx(Modal.Content, {
      children: jsx(ErrorTextWrapper, {
        "data-testid": "error-message-body",
        children: errorMessage
      })
    }), jsx(Modal.Footer, {
      children: jsx(ActionButton, {
        label: "Close",
        clickHandler: onClose,
        "data-testid": "info-modal-close"
      })
    })]
  });
};
var EditorWrapper = createStyled("div", {
  target: "embh3ih3"
} )(function() {
  return {
    height: "100%"
  };
}, "" );
var TopMenuRightWrapper = createStyled("div", {
  target: "embh3ih2"
} )(function() {
  return {
    display: "flex",
    alignItems: "center"
  };
}, "" );
var TogglerComponentWrapper = createStyled("div", {
  target: "embh3ih1"
} )(function() {
  return {
    background: "",
    "&.toggler-component-wrapper--disabled": {
      opacity: 0.4,
      pointerEvents: "none",
      cursor: "default"
    }
  };
}, "" );
var CanvasWrapper = createStyled("svg", {
  target: "embh3ih0"
} )(function() {
  return {
    "&.handCursor": {
      cursor: "\n      url('data:image/svg+xml;base64,PHN2ZwogICAgICAgIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgICAgICB3aWR0aD0iMjQiCiAgICAgICAgaGVpZ2h0PSIyNCIKICAgICAgICBmaWxsPSJub25lIgogICAgICAgIHZpZXdCb3g9IjAgMCAyNCAyNCI+CiAgICA8cGF0aAogICAgICAgICAgICBmaWxsPSIjMDAwIgogICAgICAgICAgICBkPSJNMjAuNDM0IDcuNjczYy0uMS0uNi0uNzEzLTEuNzMxLTIuMzItMS43MzEtLjEyNiAwLS4yNTIuMDA3LS4zNzcuMDIzdi0uNzlhMS4wMSAxLjAxIDAgMCAwLS4wNDUtLjNjLS4xNzctLjU2NC0uODc2LTEuNjMxLTIuMjYyLTEuNjMxYTIuNTk5IDIuNTk5IDAgMCAwLS42NzYuMDg2IDIuMzk0IDIuMzk0IDAgMCAwLS4xNDYtLjIzYy0uNDUzLS42NDUtMS4xODYtMS0yLjA2My0xLS44NzcgMC0xLjU4NC4zNi0yLjAyNSAxLjAxN2EyLjQ2MSAyLjQ2MSAwIDAgMC0uMzYxLjg1IDIuNjYzIDIuNjYzIDAgMCAwLS40MDgtLjAzYy0xLjQ3NCAwLTIuMTI0IDEuMTUtMi4yNjIgMS43NTdhMS4wMzQgMS4wMzQgMCAwIDAtLjAyNC4yMjJWMTEuMWwtLjEzLS4xYy0uNTg4LS41LTIuMDM0LTEuMTIxLTMuMzkxLjAyOS0xLjM1NyAxLjE1LTEuMDE1IDIuNjY0LS40MzEgMy40NTIuNDUzLjc3MyA0LjUxMiA3LjQyNSAxMC4yMjMgNy40MjUgMy4yNSAwIDQuOTEtMS41MTIgNS43MjktMi43ODFhNi4yOTEgNi4yOTEgMCAwIDAgLjk4LTIuOFY3LjgzOGMuMDAxLS4wNTYtLjAwMy0uMTEtLjAxMS0uMTY1WiIKICAgIC8+CiAgICA8cGF0aAogICAgICAgICAgICBmaWxsPSIjZmZmIgogICAgICAgICAgICBzdHJva2U9IiNmZmYiCiAgICAgICAgICAgIGQ9Ik0xOC40NDggMTYuMjE1YTQuNDc0IDQuNDc0IDAgMCAxLS43IDEuODg3Yy0uODA1IDEuMi0yLjE1MyAxLjgtNC4wMDggMS44LTQuNzY4IDAtOC40ODQtNi40MTItOC41Mi02LjQ3NmEuNjY5LjY2OSAwIDAgMC0uMDktLjEyNmMtLjI5NC0uNDA4IDAtLjY1NS4xMDctLjc0OC4yNjctLjIyNy41NC0uMjM3LjgxLS4wMzFsMS43NyAxLjQ1MmExIDEgMCAwIDAgMS42NDQtLjc2M1Y2LjA4YS4yODcuMjg3IDAgMCAxIC4yOS0uMTQ4LjQ0LjQ0IDAgMCAxIC4zNzIuMTZ2NC43YTEgMSAwIDEgMCAyIDB2LTYuNDVjLjA2OC0uMjQ4LjMtLjI0OC40MjItLjI0OC4yIDAgLjQxNC4wMzIuNDgyLjI1NXY2LjQ0YTEgMSAwIDEgMCAyIDB2LTUuMmEuNzUuNzUgMCAwIDEgLjA3NC0uMTljLjA0OS0uMDgxLjEwOC0uMTUuMzI1LS4xNWEuMzUuMzUgMCAwIDEgLjMwNy4xNXY1LjM5YTEgMSAwIDEgMCAyIDBWOC4wNDdhLjU4My41ODMgMCAwIDEgLjM3Ny0uMWMuMDY1IDAgLjI1OC4wMDYuMzM0LjA3OGwuMDA0IDguMTlaIgogICAgLz4KPC9zdmc+Cg=='),\n      auto\n    "
    },
    "&.handCursorGrabbing": {
      cursor: "\n      url('data:image/svg+xml;base64,PHN2ZwogICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICAgd2lkdGg9IjI0IgogICAgaGVpZ2h0PSIyNCIKICAgIGZpbGw9Im5vbmUiCiAgICB2aWV3Qm94PSIwIDAgMzAgMzAiCiAgPgogICAgPHBhdGgKICAgICAgZmlsbD0iI2ZmZiIKICAgICAgZD0iTTEwLjc0NCAzQzguODkgMyA3LjM4NCA0LjUyNSA3LjM4NCA2LjR2LjIyaC0uMDEyYy0xLjk5NyAwLTMuNjIyIDEuNjAyLTMuNjIyIDMuNTY4bC4wMDEgNy4wMmMwIDEuNzcgMS41MTIgMy41MTUgMy4xMTIgNS4zNjEuNzIuODMgMS45MTkgMi4yMTYgMi4wMzQgMi43MzF2MS41MjJoMTMuNDQydi0xLjU1NGMwLS41OS42MTgtMS43NyAxLjE2My0yLjgxLjkzOC0xLjc4OSAxLjk5OC0zLjgxNSAxLjk5OC01Ljk5MSAwLTMuMjU4LS4wMS02LjI0OC0uMDEtNi4yNDggMC0xLjY5Ni0xLjM5LTMuMDgtMy4xLTMuMDgtLjIwMyAwLS40LjAyLS41OTIuMDU3YTMuNjUgMy42NSAwIDAgMC0zLjAzMy0xLjYwN2MtLjM2NyAwLS43Mi4wNTMtMS4wNTUuMTUzYTMuNjM2IDMuNjM2IDAgMCAwLTMuMDktMS43MDVjLS40NDQgMC0uODcuMDgtMS4yNjQuMjI1QTMuMzQ1IDMuMzQ1IDAgMCAwIDEwLjc0NCAzWiIKICAgIC8+CiAgICA8cGF0aAogICAgICBmaWxsPSIjMDAwIgogICAgICBkPSJNMTAuNzQ0IDQuNTU0YzEgMCAxLjgwOC44MjYgMS44MDggMS44NDV2MS4xOTdjMC0xLjEwOS45MjctMi4wMDggMi4wNjgtMi4wMDggMS4xNDMgMCAyLjA2OC45IDIuMDY4IDIuMDA4djEuNTUyYzAtMS4xMS45My0yLjAwOCAyLjA3Ny0yLjAwOCAxLjE0NyAwIDIuMDc2Ljg5OSAyLjA3NiAyLjAwOHYxLjA2OEExLjU0IDEuNTQgMCAwIDEgMjIuMzkgOC42OWMuODU2IDAgMS41NDguNjg0IDEuNTQ4IDEuNTMgMCAwIC4wMSAyLjk4OC4wMSA2LjI0NCAwIDMuMjU3LTMuMTYxIDYuNjM2LTMuMTYxIDguODAySDEwLjQ1YzAtMS45NC01LjE0Ni01Ljc3My01LjE0Ni04LjA2MXYtNy4wMmMwLTEuMTEyLjkyNi0yLjAxNCAyLjA3LTIuMDE1djQuMDUxYzAgLjM0Mi4zNS42Mi43ODEuNjIuNDMyIDAgLjc4Mi0uMjc4Ljc4Mi0uNjJWNi40YzAtMS4wMi44MDktMS44NDUgMS44MDctMS44NDVabTAtMS41NTRDOC44OSAzIDcuMzg0IDQuNTI1IDcuMzg0IDYuNHYuMjJoLS4wMTJjLTEuOTk3IDAtMy42MjIgMS42MDItMy42MjIgMy41NjhsLjAwMSA3LjAyYzAgMS43NyAxLjUxMiAzLjUxNSAzLjExMiA1LjM2MS43Mi44MyAxLjkxOSAyLjIxNiAyLjAzNCAyLjczMXYxLjUyMmgxMy40NDJ2LTEuNTU0YzAtLjU5LjYxOC0xLjc3IDEuMTYzLTIuODEuOTM4LTEuNzg5IDEuOTk4LTMuODE1IDEuOTk4LTUuOTkxIDAtMy4yNTgtLjAxLTYuMjQ4LS4wMS02LjI0OCAwLTEuNjk2LTEuMzktMy4wOC0zLjEtMy4wOC0uMjAzIDAtLjQuMDItLjU5Mi4wNTdhMy42NSAzLjY1IDAgMCAwLTMuMDMzLTEuNjA3Yy0uMzY3IDAtLjcyLjA1My0xLjA1NS4xNTNhMy42MzYgMy42MzYgMCAwIDAtMy4wOS0xLjcwNWMtLjQ0NCAwLS44Ny4wOC0xLjI2NC4yMjVBMy4zNDUgMy4zNDUgMCAwIDAgMTAuNzQ0IDNaIgogICAgLz4KICA8L3N2Zz4='),\n      auto\n    "
    }
  };
}, "" );
function useLoading() {
  var _ketcher7;
  var ketcherId = useAppSelector(selectKetcherId);
  var _useState = reactExports.useState(false), _useState2 = _slicedToArray(_useState, 2), isLoading = _useState2[0], setIsLoading = _useState2[1];
  var ketcher;
  try {
    ketcher = ketcherProvider.getKetcher(ketcherId);
  } catch (error) {
    KetcherLogger.error("Failed to get ketcher instance with id ".concat(ketcherId), error);
  }
  var onLoadingStart = reactExports.useCallback(function() {
    return setIsLoading(true);
  }, [setIsLoading]);
  var onLoadingFinish = reactExports.useCallback(function() {
    return setIsLoading(false);
  }, [setIsLoading]);
  reactExports.useEffect(function() {
    var _ketcher, _ketcher2, _ketcher3;
    (_ketcher = ketcher) === null || _ketcher === void 0 || _ketcher.eventBus.addListener(KetcherAsyncEvents.LOADING, onLoadingStart);
    (_ketcher2 = ketcher) === null || _ketcher2 === void 0 || _ketcher2.eventBus.addListener(KetcherAsyncEvents.SUCCESS, onLoadingFinish);
    (_ketcher3 = ketcher) === null || _ketcher3 === void 0 || _ketcher3.eventBus.addListener(KetcherAsyncEvents.FAILURE, onLoadingFinish);
    return function() {
      var _ketcher4, _ketcher5, _ketcher6;
      (_ketcher4 = ketcher) === null || _ketcher4 === void 0 || _ketcher4.eventBus.removeListener(KetcherAsyncEvents.LOADING, onLoadingStart);
      (_ketcher5 = ketcher) === null || _ketcher5 === void 0 || _ketcher5.eventBus.removeListener(KetcherAsyncEvents.SUCCESS, onLoadingFinish);
      (_ketcher6 = ketcher) === null || _ketcher6 === void 0 || _ketcher6.eventBus.removeListener(KetcherAsyncEvents.FAILURE, onLoadingFinish);
    };
  }, [(_ketcher7 = ketcher) === null || _ketcher7 === void 0 ? void 0 : _ketcher7.eventBus, onLoadingFinish, onLoadingStart]);
  return isLoading;
}
function ownKeys$6(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$6(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$6(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$6(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
function _createForOfIteratorHelper$3(r, e) {
  var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"];
  if (!t) {
    if (Array.isArray(r) || (t = _unsupportedIterableToArray$3(r)) || e) {
      t && (r = t);
      var _n = 0, F = function F2() {
      };
      return { s: F, n: function n() {
        return _n >= r.length ? { done: true } : { done: false, value: r[_n++] };
      }, e: function e3(r2) {
        throw r2;
      }, f: F };
    }
    throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.");
  }
  var o, a = true, u = false;
  return { s: function s() {
    t = t.call(r);
  }, n: function n() {
    var r2 = t.next();
    return a = r2.done, r2;
  }, e: function e3(r2) {
    u = true, o = r2;
  }, f: function f() {
    try {
      a || null == t["return"] || t["return"]();
    } finally {
      if (u) throw o;
    }
  } };
}
function _unsupportedIterableToArray$3(r, a) {
  if (r) {
    if ("string" == typeof r) return _arrayLikeToArray$3(r, a);
    var t = {}.toString.call(r).slice(8, -1);
    return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray$3(r, a) : void 0;
  }
}
function _arrayLikeToArray$3(r, a) {
  (null == a || a > r.length) && (a = r.length);
  for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e];
  return n;
}
function useSetRnaPresets() {
  var dispatch2 = useAppDispatch();
  var editor = useAppSelector(selectEditor);
  var defaultRnaPresets = useAppSelector(selectDefaultRnaPresets);
  reactExports.useEffect(function() {
    if (!editor) return;
    var monomersLibrary = editor.monomersLibrary;
    var defaultPresetsTemplates = defaultRnaPresets.length ? defaultRnaPresets : editor.defaultRnaPresetsLibraryItems;
    var defaultPresets = _toConsumableArray(getPresets(monomersLibrary, defaultPresetsTemplates, true));
    var customLabeledPresets = getCachedCustomRnaPresets();
    var customPresets = [];
    var presetsDefaultNames = defaultPresets.map(function(preset) {
      return preset.name;
    });
    if (customLabeledPresets) {
      var _iterator = _createForOfIteratorHelper$3(customLabeledPresets), _step;
      try {
        for (_iterator.s(); !(_step = _iterator.n()).done; ) {
          var customLabeledPreset = _step.value;
          var i = 0;
          var presetUniqName = customLabeledPreset.name;
          while (presetsDefaultNames.includes(presetUniqName)) {
            i++;
            presetUniqName = "".concat(customLabeledPreset.name).concat("_Copy".repeat(i));
          }
          if (presetUniqName !== customLabeledPreset.name) {
            setCachedCustomRnaPreset(_objectSpread$6(_objectSpread$6({}, customLabeledPreset), {}, {
              name: presetUniqName
            }));
          }
        }
      } catch (err) {
        _iterator.e(err);
      } finally {
        _iterator.f();
      }
      customLabeledPresets = getCachedCustomRnaPresets();
      customPresets = getPresets(monomersLibrary, customLabeledPresets);
    }
    dispatch2(loadMonomerLibrary2(monomersLibrary));
    dispatch2(setFavoriteMonomersFromLocalStorage2(null));
    dispatch2(setDefaultPresets2(defaultPresets));
    customLabeledPresets && dispatch2(setCustomPresets2(customPresets));
    dispatch2(setFavoritePresetsFromLocalStorage2());
    return function() {
      dispatch2(loadMonomerLibrary2([]));
      dispatch2(clearFavorites3());
    };
  }, [editor, defaultRnaPresets]);
}
function useMacromoleculesHotkeys() {
  reactExports.useEffect(function() {
    var HELP_LINK = "master";
    var helpUrl = "https://github.com/epam/ketcher/blob/".concat(HELP_LINK, "/documentation/help.md#ketcher-macromolecules-mode");
    var handler = function handler2(e) {
      if (e.defaultPrevented) return;
      var target = e.target;
      var isEditableTarget = !!(target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable || target.closest('[contenteditable="true"]')));
      if (isEditableTarget) return;
      var isQuestionHotkey = e.key === "?" || e.key === "/" && e.shiftKey;
      if (isQuestionHotkey && !e.repeat) {
        var _window$open, _window$open$focus;
        e.preventDefault();
        (_window$open = window.open(helpUrl, "_blank")) === null || _window$open === void 0 || (_window$open$focus = _window$open.focus) === null || _window$open$focus === void 0 || _window$open$focus.call(_window$open);
      }
    };
    window.addEventListener("keydown", handler);
    return function() {
      return window.removeEventListener("keydown", handler);
    };
  }, []);
}
var LoadingCirclesWrapper = createStyled("div", {
  target: "ex562360"
} )({
  name: "1vtgpt7",
  styles: "position:absolute;top:0;left:0;height:100%;width:100%;display:flex;justify-content:center;align-items:center"
} );
var Loader = function Loader2() {
  return jsx(LoadingCirclesWrapper, {
    children: jsx(LoadingCircles, {})
  });
};
var requestFullscreen = function requestFullscreen2(element) {
  if (element.requestFullscreen) {
    element.requestFullscreen();
  } else if (element.msRequestFullscreen) {
    element.msRequestFullscreen();
  } else if (element.mozRequestFullScreen) {
    element.mozRequestFullScreen();
  } else if (element.webkitRequestFullscreen) {
    element.webkitRequestFullscreen();
  }
};
var exitFullscreen = function exitFullscreen2() {
  if (document.exitFullscreen) {
    document.exitFullscreen();
  } else if (document.msExitFullscreen) {
    document.msExitFullscreen();
  } else if (document.mozCancelFullScreen) {
    document.mozCancelFullScreen();
  } else if (document.webkitExitFullscreen) {
    document.webkitExitFullscreen();
  }
};
var isFullScreen = function isFullScreen2() {
  return !!(document.fullscreenElement || document.mozFullScreenElement || document.webkitFullscreenElement || document.msFullscreenElement);
};
var ButtonContainer = createStyled("div", {
  target: "e1yct69a0"
} )({
  name: "14ocoqf",
  styles: "display:flex;& svg:first-of-type{display:flex;justify-content:center;align-items:center;width:24px;height:24px;padding:2px;border-radius:4px;}"
} );
var FullscreenButton = function FullscreenButton2(props) {
  var _useState = reactExports.useState(isFullScreen), _useState2 = _slicedToArray(_useState, 2), fullScreenMode = _useState2[0], setFullScreenMode = _useState2[1];
  reactExports.useEffect(function() {
    var syncFullscreenMode = function syncFullscreenMode2() {
      return setFullScreenMode(isFullScreen());
    };
    document.addEventListener("fullscreenchange", syncFullscreenMode);
    document.addEventListener("webkitfullscreenchange", syncFullscreenMode);
    document.addEventListener("mozfullscreenchange", syncFullscreenMode);
    document.addEventListener("MSFullscreenChange", syncFullscreenMode);
    return function() {
      document.removeEventListener("fullscreenchange", syncFullscreenMode);
      document.removeEventListener("webkitfullscreenchange", syncFullscreenMode);
      document.removeEventListener("mozfullscreenchange", syncFullscreenMode);
      document.removeEventListener("MSFullscreenChange", syncFullscreenMode);
    };
  }, []);
  var toggleFullscreen = function toggleFullscreen2() {
    var fullscreenElement = getFullscreenElement();
    isFullScreen() ? exitFullscreen() : requestFullscreen(fullscreenElement);
  };
  return jsx(ButtonContainer, {
    className: props.className,
    children: jsx(IconButton, {
      onClick: toggleFullscreen,
      iconName: fullScreenMode ? "fullscreen-exit" : "fullscreen-enter",
      testId: "fullscreen-mode-button"
    })
  });
};
var useMenuContext = function useMenuContext2() {
  return React__default.useContext(MenuContext$1);
};
var StyledIconButton = createStyled(IconButton, {
  target: "e1erwxoo0"
} )({
  name: "1y95nj0",
  styles: "margin:2px;outline:none"
} );
function blurActiveElement() {
  var _document$activeEleme;
  (_document$activeEleme = document.activeElement) === null || _document$activeEleme === void 0 || _document$activeEleme.blur();
}
var MenuButton = createStyled(Button$1, {
  target: "e1ann9o40"
} )({
  name: "2gmlyg",
  styles: "display:flex;justify-content:space-between;font-weight:400;font-size:12px;line-height:14px;padding:7px 8px;text-transform:none;color:#333333;width:max-content"
} );
var MenuItem = function MenuItem2(_ref3) {
  var itemId = _ref3.itemId, _ref$title = _ref3.title, title = _ref$title === void 0 ? "" : _ref$title, disabled = _ref3.disabled, testId = _ref3.testId, onClick = _ref3.onClick, _ref$type = _ref3.type, type = _ref$type === void 0 ? "icon-button" : _ref$type;
  var _useMenuContext = useMenuContext(), isActive = _useMenuContext.isActive, activate = _useMenuContext.activate;
  var onClickCallback = reactExports.useCallback(function() {
    activate(itemId);
    blurActiveElement();
    if (onClick) {
      onClick();
    }
  }, [activate, itemId]);
  var isActiveItem = isActive(itemId);
  var activeClass = isActiveItem ? " active" : "";
  return jsx(Fragment, {
    children: type === "icon-button" ? jsx(StyledIconButton, {
      title,
      className: itemId + activeClass,
      isActive: isActiveItem,
      onClick: onClickCallback,
      iconName: itemId,
      testId,
      disabled
    }) : jsx(MenuButton, {
      title,
      onClick: onClickCallback,
      disabled,
      "data-testid": testId,
      children: title
    })
  });
};
var StyledDropdownIcon = createStyled(Icon, {
  shouldForwardProp: function shouldForwardProp5(prop) {
    return prop !== "isActive";
  },
  target: "e13kdqxv4"
} )("position:absolute;height:7px;width:7px;right:3px;bottom:3px;cursor:pointer;path{fill:", function(_ref3) {
  var isActive = _ref3.isActive;
  return isActive ? "white" : void 0;
}, ";}" + ("" ));
var RootContainer = createStyled("div", {
  target: "e13kdqxv3"
} )({
  name: "k5saax",
  styles: "display:flex;position:relative;align-items:center;&:active{.dropdown{fill:white;}}"
} );
var OptionsContainer = createStyled("div", {
  target: "e13kdqxv2"
} )("display:flex;border-radius:4px;flex-direction:", function(_ref22) {
  var isVertical = _ref22.isVertical;
  return isVertical ? "column" : "row";
}, ";z-index:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.zIndex.overlay;
}, ";background-color:white;padding:2px;width:", function(_ref4) {
  var isVertical = _ref4.isVertical, isAutoSize = _ref4.isAutoSize;
  return isVertical && !isAutoSize ? "38px" : "auto";
}, ";height:", function(_ref5) {
  var isVertical = _ref5.isVertical, isAutoSize = _ref5.isAutoSize;
  return isVertical || isAutoSize ? "auto" : "38px";
}, ";" + ("" ));
var OptionsItemsCollapse = createStyled(Collapse, {
  target: "e13kdqxv1"
} )("position:absolute;z-index:", function(_ref6) {
  var theme = _ref6.theme;
  return theme.ketcher.zIndex.overlay;
}, ";" + ("" ));
var VisibleItem = createStyled("div", {
  target: "e13kdqxv0"
} )({
  name: "a1qh1t",
  styles: "display:flex;align-items:center;position:relative;width:32px;height:32px;padding:0;justify-content:center;border-radius:2px"
} );
function ownKeys$5(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$5(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$5(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$5(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var SubMenu = function SubMenu2(_ref3) {
  var children2 = _ref3.children, _ref$vertical = _ref3.vertical, vertical = _ref$vertical === void 0 ? false : _ref$vertical, _ref$autoSize = _ref3.autoSize, autoSize = _ref$autoSize === void 0 ? false : _ref$autoSize, _ref$disabled = _ref3.disabled, disabled = _ref$disabled === void 0 ? false : _ref$disabled, _ref$needOpenByMenuIt = _ref3.needOpenByMenuItemClick, needOpenByMenuItemClick = _ref$needOpenByMenuIt === void 0 ? false : _ref$needOpenByMenuIt, testId = _ref3.testId, _ref$layoutModeButton = _ref3.layoutModeButton, layoutModeButton = _ref$layoutModeButton === void 0 ? false : _ref$layoutModeButton, generalTitle = _ref3.generalTitle, activeItem = _ref3.activeItem, subMenuId = _ref3.subMenuId;
  var dispatch2 = useAppDispatch();
  var ref = reactExports.useRef(null);
  var _useState = reactExports.useState(false), _useState2 = _slicedToArray(_useState, 2), open = _useState2[0], setOpen = _useState2[1];
  var _useMenuContext = useMenuContext(), isActive = _useMenuContext.isActive;
  var _usePortalStyle = usePortalStyle([ref, open, vertical, KETCHER_MACROMOLECULES_ROOT_NODE_SELECTOR]), _usePortalStyle2 = _slicedToArray(_usePortalStyle, 1), portalStyle = _usePortalStyle2[0];
  var selectedMenuGroupItem = useAppSelector(
    selectSelectedMenuGroupItem(subMenuId)
  );
  var lastActiveOption = subMenuId ? selectedMenuGroupItem : null;
  var handleDropDownClick = function handleDropDownClick2() {
    if (disabled) return;
    setOpen(function(prev) {
      return !prev;
    });
  };
  var hideCollapse = function hideCollapse2() {
    open && setOpen(false);
  };
  var subComponents = React__default.Children.map(children2, function(child) {
    return child.type === MenuItem ? child : null;
  });
  var options2 = subComponents.map(function(item) {
    return item.props.itemId;
  }).filter(function(item) {
    return item;
  });
  var activeOptions = options2.filter(function(itemKey) {
    return isActive(itemKey);
  });
  var activeOption = activeOptions[0];
  reactExports.useEffect(function() {
    if (subMenuId && activeOption && activeOption !== lastActiveOption) {
      dispatch2(setSelectedMenuGroupItem2({
        groupName: subMenuId,
        activeItemName: activeOption
      }));
    }
  }, [dispatch2, subMenuId, activeOption, lastActiveOption]);
  var visibleItemId = activeItem !== null && activeItem !== void 0 ? activeItem : activeOption || lastActiveOption || options2[0];
  var visibleItem = subComponents.find(function(option) {
    return option.props.itemId === visibleItemId;
  });
  var visibleItemTestId = visibleItem === null || visibleItem === void 0 ? void 0 : visibleItem.props.testId;
  var visibleItemTitle = generalTitle !== null && generalTitle !== void 0 ? generalTitle : visibleItem === null || visibleItem === void 0 ? void 0 : visibleItem.props.title;
  var ketcherEditorRootElement = document.querySelector(KETCHER_MACROMOLECULES_ROOT_NODE_SELECTOR);
  return jsx(RootContainer, {
    "data-testid": testId,
    "data-is-selected": isActive(visibleItemId) ? "true" : "false",
    ref,
    children: jsxs(Fragment, {
      children: [jsxs(VisibleItem, {
        children: [jsx(MenuItem, {
          disabled,
          itemId: visibleItemId,
          title: visibleItemTitle,
          testId: visibleItemTestId,
          onClick: needOpenByMenuItemClick ? handleDropDownClick : EmptyFunction
        }), open || jsx(StyledDropdownIcon, {
          className: "dropdown",
          name: "dropdown",
          onClick: handleDropDownClick,
          isActive: isActive(visibleItemId),
          dataTestId: "dropdown-expand"
        })]
      }), ketcherEditorRootElement && reactDomExports.createPortal(jsx(OptionsItemsCollapse, {
        "in": open,
        timeout: 0,
        style: _objectSpread$5({}, portalStyle),
        unmountOnExit: true,
        onClick: hideCollapse,
        children: jsx(ClickAwayListener, {
          onClickAway: hideCollapse,
          children: jsx(OptionsContainer, {
            isVertical: vertical,
            isAutoSize: autoSize,
            islayoutModeButton: layoutModeButton,
            "data-testid": "multi-tool-dropdown",
            children: subComponents.map(function(component) {
              return React__default.cloneElement(component, {
                key: component.props.itemId
              });
            })
          })
        })
      }), ketcherEditorRootElement)]
    })
  });
};
var MenuLayout = createStyled("div", {
  target: "e1fh0ozy3"
} )(function(_ref3) {
  var theme = _ref3.theme, isHorizontal = _ref3.isHorizontal;
  return {
    backgroundColor: theme.ketcher.color.background.primary,
    borderRadius: "4px",
    display: "flex",
    flexDirection: isHorizontal ? "row" : "column",
    zIndex: theme.ketcher.zIndex.toolbar
  };
}, "" );
var Divider = createStyled("hr", {
  target: "e1fh0ozy2"
} )("width:18px;margin:6px 0;align-self:center;border-width:thin 0px 0px 0px;border-style:solid;border-color:", function(_ref22) {
  var theme = _ref22.theme;
  return theme.ketcher.color.divider;
}, ";" + ("" ));
var VerticalDivider = createStyled("hr", {
  target: "e1fh0ozy1"
} )("height:18px;margin:0px 6px;align-self:center;border-width:0px thin 0px 0px;border-style:solid;border-color:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.color.divider;
}, ";" + ("" ));
var StyledGroup = createStyled("div", {
  target: "e1fh0ozy0"
} )(function(_ref4) {
  var theme = _ref4.theme, isHorizontal = _ref4.isHorizontal;
  return {
    display: "flex",
    flexDirection: isHorizontal ? "row" : "column",
    flexWrap: "nowrap",
    alignItems: "center",
    backgroundColor: theme.ketcher.color.background.primary,
    borderRadius: "2px",
    width: isHorizontal ? void 0 : "32px",
    marginBottom: isHorizontal ? void 0 : "8px",
    "> :last-child": isHorizontal ? void 0 : {
      marginBottom: 0
    }
  };
}, "" );
var Group = function Group2(_ref3) {
  var children2 = _ref3.children, _ref$divider = _ref3.divider, divider = _ref$divider === void 0 ? false : _ref$divider, isHorizontal = _ref3.isHorizontal;
  var subComponents = React__default.Children.map(children2, function(child) {
    return child;
  });
  return jsxs(Fragment, {
    children: [jsx(StyledGroup, {
      isHorizontal,
      children: subComponents
    }), divider && (isHorizontal ? jsx(VerticalDivider, {}) : jsx(Divider, {}))]
  });
};
var Menu = function Menu2(_ref22) {
  var children2 = _ref22.children, onItemClick = _ref22.onItemClick, activeMenuItems = _ref22.activeMenuItems, testId = _ref22.testId, isHorizontal = _ref22.isHorizontal;
  var context = React__default.useMemo(function() {
    return {
      isActive: function isActive(itemKey) {
        return activeMenuItems ? activeMenuItems.includes(itemKey) : false;
      },
      activate: function activate(itemKey) {
        onItemClick(itemKey);
      }
    };
  }, [activeMenuItems, onItemClick]);
  var subComponents = React__default.Children.map(children2, function(child) {
    return child && child.type === Group ? child : null;
  });
  return jsx(MenuContext$1.Provider, {
    value: context,
    children: jsx(MenuLayout, {
      "data-testid": testId,
      isHorizontal,
      children: subComponents
    })
  });
};
Menu.Group = Group;
Menu.Item = MenuItem;
Menu.Submenu = SubMenu;
var LayoutModeButton = function LayoutModeButton2() {
  var editor = useAppSelector(selectEditor);
  var layoutMode = useLayoutMode();
  var _useState = reactExports.useState(layoutMode), _useState2 = _slicedToArray(_useState, 2), activeMode = _useState2[0], setActiveMode = _useState2[1];
  var isSequenceEditInRNABuilderMode = useAppSelector(selectIsSequenceEditInRNABuilderMode);
  var menuContext = reactExports.useMemo(function() {
    return {
      isActive: function isActive(mode) {
        return activeMode === mode;
      },
      activate: function activate(mode) {
        if (mode === activeMode) {
          return;
        }
        setActiveMode(mode);
        editor === null || editor === void 0 || editor.events.selectMode.dispatch(mode);
        editor === null || editor === void 0 || editor.events.layoutModeChange.dispatch(mode);
      }
    };
  }, [activeMode, editor]);
  reactExports.useEffect(function() {
    setActiveMode(layoutMode);
  }, [layoutMode]);
  return jsx(MenuContext$1.Provider, {
    value: menuContext,
    children: jsxs(Menu.Submenu, {
      disabled: isSequenceEditInRNABuilderMode,
      testId: "layout-mode",
      vertical: true,
      needOpenByMenuItemClick: true,
      layoutModeButton: true,
      children: [jsx(Menu.Item, {
        itemId: "sequence-layout-mode",
        testId: "sequence-layout-mode",
        title: "Switch to sequence layout mode"
      }), jsx(Menu.Item, {
        itemId: "snake-layout-mode",
        testId: "snake-layout-mode",
        title: "Switch to snake layout mode"
      }), jsx(Menu.Item, {
        itemId: "flex-layout-mode",
        testId: "flex-layout-mode",
        title: "Switch to flex layout mode"
      })]
    })
  });
};
function _createForOfIteratorHelper$2(r, e) {
  var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"];
  if (!t) {
    if (Array.isArray(r) || (t = _unsupportedIterableToArray$2(r)) || e) {
      t && (r = t);
      var _n = 0, F = function F2() {
      };
      return { s: F, n: function n() {
        return _n >= r.length ? { done: true } : { done: false, value: r[_n++] };
      }, e: function e3(r2) {
        throw r2;
      }, f: F };
    }
    throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.");
  }
  var o, a = true, u = false;
  return { s: function s() {
    t = t.call(r);
  }, n: function n() {
    var r2 = t.next();
    return a = r2.done, r2;
  }, e: function e3(r2) {
    u = true, o = r2;
  }, f: function f() {
    try {
      a || null == t["return"] || t["return"]();
    } finally {
      if (u) throw o;
    }
  } };
}
function _unsupportedIterableToArray$2(r, a) {
  if (r) {
    if ("string" == typeof r) return _arrayLikeToArray$2(r, a);
    var t = {}.toString.call(r).slice(8, -1);
    return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray$2(r, a) : void 0;
  }
}
function _arrayLikeToArray$2(r, a) {
  (null == a || a > r.length) && (a = r.length);
  for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e];
  return n;
}
var generateLabeledNodes = function generateLabeledNodes2(selectionsFlatten) {
  var labeledNodes = [];
  var _iterator = _createForOfIteratorHelper$2(selectionsFlatten), _step;
  try {
    for (_iterator.s(); !(_step = _iterator.n()).done; ) {
      var selection2 = _step.value;
      var node = selection2.node, nodeIndexOverall = selection2.nodeIndexOverall, isNucleosideConnectedAndSelectedWithPhosphate = selection2.isNucleosideConnectedAndSelectedWithPhosphate, hasR1Connection = selection2.hasR1Connection, twoStrandedNode = selection2.twoStrandedNode;
      var hasAntisense = Boolean(twoStrandedNode === null || twoStrandedNode === void 0 ? void 0 : twoStrandedNode.antisenseNode);
      if (node instanceof Nucleotide) {
        var _node$rnaBase, _node$sugar, _node$phosphate;
        labeledNodes.push({
          type: Entities.Nucleotide,
          baseLabel: node === null || node === void 0 || (_node$rnaBase = node.rnaBase) === null || _node$rnaBase === void 0 ? void 0 : _node$rnaBase.label,
          sugarLabel: node === null || node === void 0 || (_node$sugar = node.sugar) === null || _node$sugar === void 0 ? void 0 : _node$sugar.label,
          phosphateLabel: node === null || node === void 0 || (_node$phosphate = node.phosphate) === null || _node$phosphate === void 0 ? void 0 : _node$phosphate.label,
          rnaBaseMonomerItem: node.rnaBase instanceof AmbiguousMonomer ? node.rnaBase.variantMonomerItem : node.rnaBase.monomerItem,
          hasR1Connection,
          nodeIndexOverall,
          hasAntisense
        });
      } else if (node instanceof Nucleoside) {
        var _node$rnaBase2, _node$sugar2;
        labeledNodes.push({
          type: Entities.Nucleoside,
          baseLabel: node === null || node === void 0 || (_node$rnaBase2 = node.rnaBase) === null || _node$rnaBase2 === void 0 ? void 0 : _node$rnaBase2.label,
          sugarLabel: node === null || node === void 0 || (_node$sugar2 = node.sugar) === null || _node$sugar2 === void 0 ? void 0 : _node$sugar2.label,
          rnaBaseMonomerItem: node.rnaBase instanceof AmbiguousMonomer ? node.rnaBase.variantMonomerItem : node.rnaBase.monomerItem,
          isNucleosideConnectedAndSelectedWithPhosphate,
          hasR1Connection,
          nodeIndexOverall,
          hasAntisense
        });
      } else if ((node === null || node === void 0 ? void 0 : node.monomer) instanceof Phosphate) {
        var _node$monomer;
        labeledNodes.push({
          type: Entities.Phosphate,
          phosphateLabel: node === null || node === void 0 || (_node$monomer = node.monomer) === null || _node$monomer === void 0 ? void 0 : _node$monomer.label,
          nodeIndexOverall,
          hasAntisense
        });
      }
    }
  } catch (err) {
    _iterator.e(err);
  } finally {
    _iterator.f();
  }
  return labeledNodes;
};
function isNucleotideNucleosideOrPhosphate(selection2) {
  var node = selection2.node;
  return node instanceof Nucleotide || node instanceof Nucleoside || (node === null || node === void 0 ? void 0 : node.monomer) instanceof Phosphate;
}
var generateNucleoelementTitle = function generateNucleoelementTitle2(elements) {
  var tempTitle = "";
  var element = elements.length === 1 ? elements[0] : lodashExports.merge.apply(void 0, [{}].concat(_toConsumableArray(elements)));
  for (var _i = 0, _arr = ["sugarLabel", "baseLabel", "phosphateLabel"]; _i < _arr.length; _i++) {
    var property = _arr[_i];
    var label = lodashExports.get(element, property, "");
    if (property === "baseLabel") {
      tempTitle += "(".concat(label, ")");
    } else {
      tempTitle += label;
    }
  }
  return tempTitle;
};
var generateSequenceContextMenuProps = function generateSequenceContextMenuProps2(selections) {
  if (!(selections !== null && selections !== void 0 && selections.length)) return;
  var selectionsFlatten = lodashExports.flatten(selections);
  var countOfSelections = selectionsFlatten.length;
  var countOfNucleoelements = getCountOfNucleoelements(selectionsFlatten);
  var title;
  var isSelectedAtLeastOneNucleoelement = false;
  var isSelectedOnlyNucleoelements = true;
  var hasAntisense = false;
  var isSequenceFirstsOnlyNucleoelementsSelected = true;
  var selectedSequenceLabeledNodes = generateLabeledNodes(selectionsFlatten);
  for (var i = 0; i < selectedSequenceLabeledNodes.length; i++) {
    var node = selectedSequenceLabeledNodes[i];
    var prevNode = selectedSequenceLabeledNodes[i - 1];
    var isNodeNucleotideOrNucleoside = node.type === Entities.Nucleotide || node.type === Entities.Nucleoside;
    var isNucleotideConnection = prevNode === null || prevNode === void 0 ? void 0 : prevNode.isNucleosideConnectedAndSelectedWithPhosphate;
    if (isNodeNucleotideOrNucleoside) {
      isSelectedAtLeastOneNucleoelement = true;
    }
    if (isNodeNucleotideOrNucleoside || isNucleotideConnection) {
      if (node.hasR1Connection) isSequenceFirstsOnlyNucleoelementsSelected = false;
    } else {
      isSequenceFirstsOnlyNucleoelementsSelected = false;
      isSelectedOnlyNucleoelements = false;
    }
    if (node.hasAntisense) {
      hasAntisense = true;
    }
  }
  if (countOfSelections > countOfNucleoelements) {
    if (!selectionsFlatten.every(isNucleotideNucleosideOrPhosphate)) {
      isSelectedOnlyNucleoelements = false;
    }
  }
  if (countOfSelections === 1 || countOfNucleoelements === 1 && isSelectedOnlyNucleoelements) {
    title = generateNucleoelementTitle(selectedSequenceLabeledNodes);
  } else {
    title = isSelectedOnlyNucleoelements ? "".concat(countOfNucleoelements, " nucleotides") : "".concat(countOfSelections, " elements");
  }
  return {
    title,
    selectedSequenceLabeledNodes,
    isSelectedOnlyNucleoelements,
    isSelectedAtLeastOneNucleoelement,
    isSequenceFirstsOnlyNucleoelementsSelected,
    hasAntisense
  };
};
function isEstablishHydrogenBondDisabled() {
  var selections = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : [];
  return selections.every(function(selectionRange) {
    return selectionRange.every(function(selection2) {
      return isTwoStrandedNodeRestrictedForHydrogenBondCreation(selection2.twoStrandedNode);
    });
  });
}
function isNodeContainHydrogenBonds(node) {
  return node === null || node === void 0 ? void 0 : node.monomers.some(function(monomer) {
    return monomer.hydrogenBonds.length !== 0;
  });
}
function _createForOfIteratorHelper$1(r, e) {
  var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"];
  if (!t) {
    if (Array.isArray(r) || (t = _unsupportedIterableToArray$1(r)) || e) {
      t && (r = t);
      var _n = 0, F = function F2() {
      };
      return { s: F, n: function n() {
        return _n >= r.length ? { done: true } : { done: false, value: r[_n++] };
      }, e: function e3(r2) {
        throw r2;
      }, f: F };
    }
    throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.");
  }
  var o, a = true, u = false;
  return { s: function s() {
    t = t.call(r);
  }, n: function n() {
    var r2 = t.next();
    return a = r2.done, r2;
  }, e: function e3(r2) {
    u = true, o = r2;
  }, f: function f() {
    try {
      a || null == t["return"] || t["return"]();
    } finally {
      if (u) throw o;
    }
  } };
}
function _unsupportedIterableToArray$1(r, a) {
  if (r) {
    if ("string" == typeof r) return _arrayLikeToArray$1(r, a);
    var t = {}.toString.call(r).slice(8, -1);
    return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray$1(r, a) : void 0;
  }
}
function _arrayLikeToArray$1(r, a) {
  (null == a || a > r.length) && (a = r.length);
  for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e];
  return n;
}
var getMonomersCode = function getMonomersCode2(monomers) {
  return monomers.map(function(monomer) {
    return monomer.monomerItem.props.MonomerNaturalAnalogCode;
  }).sort(function(a, b) {
    return a.localeCompare(b);
  }).join("");
};
var isSenseBase = function isSenseBase2(monomer) {
  var monomerItem = monomer.monomerItem;
  var isNaturalAnalogue = monomerItem.props.MonomerNaturalAnalogCode === "A" || monomerItem.props.MonomerNaturalAnalogCode === "C" || monomerItem.props.MonomerNaturalAnalogCode === "G" || monomerItem.props.MonomerNaturalAnalogCode === "T" || monomerItem.props.MonomerNaturalAnalogCode === "U";
  if (isNaturalAnalogue) {
    return true;
  }
  if (!monomer.monomerItem.isAmbiguous) {
    return false;
  }
  if (monomer.subtype === KetAmbiguousMonomerTemplateSubType.MIXTURE) {
    return false;
  }
  var N1 = "ACGT";
  var N2 = "ACGU";
  var B1 = "CGT";
  var B2 = "CGU";
  var D1 = "AGT";
  var D2 = "AGU";
  var H1 = "ACT";
  var H2 = "ACU";
  var K1 = "GT";
  var K2 = "GU";
  var W1 = "AT";
  var W2 = "AU";
  var Y1 = "CT";
  var Y2 = "CU";
  var M = "AC";
  var R = "AG";
  var S = "CG";
  var V = "ACG";
  var ambigues = [N1, N2, B1, B2, D1, D2, H1, H2, K1, K2, W1, W2, Y1, Y2, M, R, S, V];
  var code = getMonomersCode(monomer.monomers);
  return ambigues.some(function(v) {
    return v === code;
  });
};
var isAntisenseCreationDisabled = function isAntisenseCreationDisabled2(selectedMonomers) {
  return selectedMonomers === null || selectedMonomers === void 0 ? void 0 : selectedMonomers.some(function(selectedMonomer) {
    var rnaBaseForSugar = selectedMonomer instanceof Sugar && getRnaBaseFromSugar(selectedMonomer);
    return selectedMonomer instanceof RNABase && (selectedMonomer.hydrogenBonds.length > 0 || selectedMonomer.covalentBonds.length > 1) || isRnaBaseOrAmbiguousRnaBase2(selectedMonomer) && !isSenseBase(selectedMonomer) || rnaBaseForSugar && (rnaBaseForSugar.hydrogenBonds.length > 0 || rnaBaseForSugar.covalentBonds.length > 1 || !isSenseBase(rnaBaseForSugar));
  });
};
var hasOnlyDeoxyriboseSugars = function hasOnlyDeoxyriboseSugars2(selectedMonomers) {
  return selectedMonomers === null || selectedMonomers === void 0 ? void 0 : selectedMonomers.every(function(selectedMonomer) {
    return selectedMonomer instanceof Sugar ? selectedMonomer.label === RNA_DNA_NON_MODIFIED_PART.SUGAR_DNA : true;
  });
};
var hasOnlyRiboseSugars = function hasOnlyRiboseSugars2(selectedMonomers) {
  return selectedMonomers === null || selectedMonomers === void 0 ? void 0 : selectedMonomers.every(function(selectedMonomer) {
    return selectedMonomer instanceof Sugar ? selectedMonomer.label === RNA_DNA_NON_MODIFIED_PART.SUGAR_RNA : true;
  });
};
var isAntisenseOptionVisible = function isAntisenseOptionVisible2(selectedMonomers) {
  return selectedMonomers === null || selectedMonomers === void 0 ? void 0 : selectedMonomers.some(function(selectedMonomer) {
    return selectedMonomer instanceof RNABase && getSugarFromRnaBase2(selectedMonomer) || isSugarOrAmbiguousSugar(selectedMonomer) && getRnaBaseFromSugar(selectedMonomer);
  });
};
var AMINO_ACID_MODIFICATION_MENU_ITEM_PREFIX = "aminoAcidModification-";
var getModifyAminoAcidsMenuItems = function getModifyAminoAcidsMenuItems2(selectedMonomers) {
  var modificationsForSelection = /* @__PURE__ */ new Set();
  var modificationTypesDisabledByAttachmentPoints = /* @__PURE__ */ new Set();
  var naturalAnalogueToSelectedMonomers = /* @__PURE__ */ new Map();
  var editor = provideEditorInstance();
  selectedMonomers.forEach(function(selectedMonomer) {
    var _naturalAnalogueToSel;
    var monomerNaturalAnalogCode = selectedMonomer.monomerItem.props.MonomerNaturalAnalogCode;
    if (!(selectedMonomer instanceof Peptide) || !monomerNaturalAnalogCode) {
      return;
    }
    if (!naturalAnalogueToSelectedMonomers.has(monomerNaturalAnalogCode)) {
      naturalAnalogueToSelectedMonomers.set(monomerNaturalAnalogCode, []);
    }
    (_naturalAnalogueToSel = naturalAnalogueToSelectedMonomers.get(monomerNaturalAnalogCode)) === null || _naturalAnalogueToSel === void 0 || _naturalAnalogueToSel.push(selectedMonomer);
  });
  editor === null || editor === void 0 || editor.monomersLibrary.forEach(function(monomerLibraryItem) {
    var _monomerLibraryItem$p;
    var monomersWithSameNaturalAnalogCode = naturalAnalogueToSelectedMonomers.get((_monomerLibraryItem$p = monomerLibraryItem.props) === null || _monomerLibraryItem$p === void 0 ? void 0 : _monomerLibraryItem$p.MonomerNaturalAnalogCode);
    if (!monomerLibraryItem.props || !monomersWithSameNaturalAnalogCode) {
      return;
    }
    var modificationTypes = monomerLibraryItem.props.modificationTypes;
    if (!modificationTypes) {
      return;
    }
    modificationTypes.forEach(function(modificationType) {
      if (monomersWithSameNaturalAnalogCode.every(function(monomer) {
        return monomer.label === monomerLibraryItem.label;
      })) {
        return;
      }
      var hasAtLeastOneEligibleMonomer = monomersWithSameNaturalAnalogCode.some(function(monomer) {
        return monomer.label !== monomerLibraryItem.label && canModifyAminoAcid(monomer, monomerLibraryItem);
      });
      if (!hasAtLeastOneEligibleMonomer) {
        modificationTypesDisabledByAttachmentPoints.add(modificationType);
        return;
      }
      modificationsForSelection.add(modificationType);
    });
  });
  var menuItems = _toConsumableArray(modificationsForSelection.values()).filter(function(modificationType) {
    return !modificationTypesDisabledByAttachmentPoints.has(modificationType);
  }).map(function(modificationType) {
    var aminoAcidsToModify = getAminoAcidsToModify(selectedMonomers, modificationType, editor.monomersLibrary);
    return {
      name: "".concat(AMINO_ACID_MODIFICATION_MENU_ITEM_PREFIX).concat(modificationType),
      title: modificationType,
      onMouseOver: function onMouseOver() {
        editor.transientDrawingView.showModifyAminoAcidsView({
          monomersToModify: _toConsumableArray(aminoAcidsToModify.keys())
        });
        editor.transientDrawingView.update();
      },
      onMouseOut: function onMouseOut() {
        editor.transientDrawingView.hideModifyAminoAcidsView();
        editor.transientDrawingView.update();
      }
    };
  });
  menuItems.sort(compareByTitleWithNaturalFirst);
  return menuItems;
};
var getMonomersForAminoAcidModification = function getMonomersForAminoAcidModification2(selectedMonomers, contextMenuEvent) {
  var _contextMenuEvent$tar, _clickedSequenceItemR;
  var clickedSequenceItemRenderer = contextMenuEvent === null || contextMenuEvent === void 0 || (_contextMenuEvent$tar = contextMenuEvent.target) === null || _contextMenuEvent$tar === void 0 ? void 0 : _contextMenuEvent$tar.__data__;
  var clickedMonomer = clickedSequenceItemRenderer === null || clickedSequenceItemRenderer === void 0 || (_clickedSequenceItemR = clickedSequenceItemRenderer.node) === null || _clickedSequenceItemR === void 0 ? void 0 : _clickedSequenceItemR.monomer;
  var monomerCandidates = [];
  if (selectedMonomers.length) {
    monomerCandidates = selectedMonomers;
  } else if (clickedMonomer) {
    monomerCandidates = [clickedMonomer];
  }
  var monomersForAminoAcidModification = monomerCandidates.filter(function(monomer) {
    return monomer instanceof Peptide;
  });
  return monomersForAminoAcidModification;
};
var isCycleExistsForSelectedMonomers = function isCycleExistsForSelectedMonomers2(selectedMonomers) {
  if (selectedMonomers.length < 3) {
    return false;
  }
  var monomerSet = new Set(selectedMonomers);
  var visited = /* @__PURE__ */ new Set();
  var inRecursionStack = /* @__PURE__ */ new Set();
  var getNeighbors = function getNeighbors2(monomer2) {
    var neighbors = [];
    monomer2.forEachBond(function(bond) {
      if (bond instanceof MonomerToAtomBond) {
        return;
      }
      var firstMonomer = bond.firstMonomer;
      var secondMonomer = bond.secondMonomer;
      if (!firstMonomer || !secondMonomer) {
        return;
      }
      var neighbor = bond.getAnotherMonomer(monomer2);
      if (neighbor && monomerSet.has(neighbor)) {
        neighbors.push(neighbor);
      }
    });
    return neighbors;
  };
  var dfs = function dfs2(monomer2, parent) {
    visited.add(monomer2);
    inRecursionStack.add(monomer2);
    var neighbors = getNeighbors(monomer2);
    var _iterator = _createForOfIteratorHelper$1(neighbors), _step;
    try {
      for (_iterator.s(); !(_step = _iterator.n()).done; ) {
        var neighbor = _step.value;
        if (neighbor === parent) {
          continue;
        }
        if (inRecursionStack.has(neighbor)) {
          return true;
        }
        if (!visited.has(neighbor)) {
          if (dfs2(neighbor, monomer2)) {
            return true;
          }
        }
      }
    } catch (err) {
      _iterator.e(err);
    } finally {
      _iterator.f();
    }
    inRecursionStack["delete"](monomer2);
    return false;
  };
  var _iterator2 = _createForOfIteratorHelper$1(selectedMonomers), _step2;
  try {
    for (_iterator2.s(); !(_step2 = _iterator2.n()).done; ) {
      var monomer = _step2.value;
      if (!visited.has(monomer)) {
        if (dfs(monomer, null)) {
          return true;
        }
      }
    }
  } catch (err) {
    _iterator2.e(err);
  } finally {
    _iterator2.f();
  }
  return false;
};
var SequenceItemContextMenuNames;
(function(SequenceItemContextMenuNames2) {
  SequenceItemContextMenuNames2["title"] = "sequence_menu_title";
  SequenceItemContextMenuNames2["createRnaAntisenseStrand"] = "create_antisense_rna_chain";
  SequenceItemContextMenuNames2["createDnaAntisenseStrand"] = "create_antisense_dna_chain";
  SequenceItemContextMenuNames2["modifyInRnaBuilder"] = "modify_in_rna_builder";
  SequenceItemContextMenuNames2["modifyAminoAcids"] = "modify_amino_acids";
  SequenceItemContextMenuNames2["establishHydrogenBond"] = "establish_hydrogen_bond";
  SequenceItemContextMenuNames2["deleteHydrogenBond"] = "delete_hydrogen_bond";
  SequenceItemContextMenuNames2["editSequence"] = "edit_sequence";
  SequenceItemContextMenuNames2["startNewSequence"] = "start_new_sequence";
  SequenceItemContextMenuNames2["copy"] = "copy";
  SequenceItemContextMenuNames2["paste"] = "paste";
  SequenceItemContextMenuNames2["delete"] = "delete";
})(SequenceItemContextMenuNames || (SequenceItemContextMenuNames = {}));
var SequenceItemContextMenu = function SequenceItemContextMenu2(_ref3) {
  var _selections$flat, _selections$some;
  var selections = _ref3.selections, contextMenuEvent = _ref3.contextMenuEvent;
  var editor = useAppSelector(selectEditor);
  var dispatch2 = useAppDispatch();
  var menuProps = generateSequenceContextMenuProps(selections);
  var selectedMonomers = (selections === null || selections === void 0 || (_selections$flat = selections.flat()) === null || _selections$flat === void 0 ? void 0 : _selections$flat.flatMap(function(nodeSelection) {
    return nodeSelection.node.monomers;
  })) || [];
  var monomersForAminoAcidModification = getMonomersForAminoAcidModification(selectedMonomers, contextMenuEvent);
  var isSequenceEditInRNABuilderMode = useAppSelector(selectIsSequenceEditInRNABuilderMode);
  var isSequenceMode = useLayoutMode() === "sequence-layout-mode";
  var modifyAminoAcidsMenuItems = getModifyAminoAcidsMenuItems(monomersForAminoAcidModification);
  var hasHydrogenBonds = (_selections$some = selections === null || selections === void 0 ? void 0 : selections.some(function(selectionRange) {
    return selectionRange.some(function(selection2) {
      return isNodeContainHydrogenBonds(selection2.node);
    });
  })) !== null && _selections$some !== void 0 ? _selections$some : false;
  var isAntisenseBlockVisible = (selectedMonomers === null || selectedMonomers === void 0 ? void 0 : selectedMonomers.length) > 0 && isAntisenseOptionVisible(selectedMonomers);
  var isHydrogenBondBlockVisible = !isEstablishHydrogenBondDisabled(selections) || hasHydrogenBonds;
  var menuItems = [{
    name: SequenceItemContextMenuNames.title,
    title: menuProps === null || menuProps === void 0 ? void 0 : menuProps.title,
    isMenuTitle: true,
    disabled: true,
    hidden: function hidden(_ref22) {
      var props = _ref22.props;
      return !(props !== null && props !== void 0 && props.sequenceItemRenderer) || !(menuProps !== null && menuProps !== void 0 && menuProps.isSelectedAtLeastOneNucleoelement);
    }
  }, {
    name: SequenceItemContextMenuNames.copy,
    title: "Copy",
    icon: jsx(Icon, {
      name: "copyMenu"
    }),
    disabled: (selectedMonomers === null || selectedMonomers === void 0 ? void 0 : selectedMonomers.length) === 0
  }, {
    name: SequenceItemContextMenuNames.paste,
    title: "Paste",
    icon: jsx(Icon, {
      name: "pasteNavBar"
    }),
    disabled: false,
    separator: true
  }, {
    name: SequenceItemContextMenuNames.editSequence,
    title: "Edit sequence",
    disabled: false,
    hidden: function hidden(_ref32) {
      var props = _ref32.props;
      return !(props !== null && props !== void 0 && props.sequenceItemRenderer);
    }
  }, {
    name: SequenceItemContextMenuNames.startNewSequence,
    title: "Start new sequence",
    disabled: false,
    separator: isAntisenseBlockVisible || isHydrogenBondBlockVisible
  }, {
    name: SequenceItemContextMenuNames.createRnaAntisenseStrand,
    title: "Create RNA antisense strand",
    disabled: isAntisenseCreationDisabled(selectedMonomers),
    hidden: function hidden() {
      return !selectedMonomers || !isAntisenseOptionVisible(selectedMonomers);
    }
  }, {
    name: SequenceItemContextMenuNames.createDnaAntisenseStrand,
    title: "Create DNA antisense strand",
    disabled: isAntisenseCreationDisabled(selectedMonomers),
    hidden: function hidden() {
      return !selectedMonomers || !isAntisenseOptionVisible(selectedMonomers);
    }
  }, {
    name: SequenceItemContextMenuNames.establishHydrogenBond,
    title: "Establish Hydrogen Bonds",
    disabled: function disabled(_ref4) {
      var _props$sequenceItemRe;
      var props = _ref4.props;
      return (selections === null || selections === void 0 ? void 0 : selections.length) === 0 ? isTwoStrandedNodeRestrictedForHydrogenBondCreation(props === null || props === void 0 || (_props$sequenceItemRe = props.sequenceItemRenderer) === null || _props$sequenceItemRe === void 0 ? void 0 : _props$sequenceItemRe.twoStrandedNode) : isEstablishHydrogenBondDisabled(selections);
    },
    hidden: function hidden(_ref5) {
      var props = _ref5.props;
      return !(props !== null && props !== void 0 && props.sequenceItemRenderer);
    }
  }, {
    name: SequenceItemContextMenuNames.deleteHydrogenBond,
    title: "Remove hydrogen bonds",
    disabled: function disabled(_ref6) {
      var _props$sequenceItemRe2;
      var props = _ref6.props;
      return (selections === null || selections === void 0 ? void 0 : selections.length) === 0 ? !isNodeContainHydrogenBonds(props === null || props === void 0 || (_props$sequenceItemRe2 = props.sequenceItemRenderer) === null || _props$sequenceItemRe2 === void 0 ? void 0 : _props$sequenceItemRe2.node) : !(selections !== null && selections !== void 0 && selections.some(function(selectionRange) {
        return selectionRange.some(function(selection2) {
          return isNodeContainHydrogenBonds(selection2.node);
        });
      }));
    },
    hidden: function hidden(_ref7) {
      var props = _ref7.props;
      return !(props !== null && props !== void 0 && props.sequenceItemRenderer);
    }
  }, {
    name: SequenceItemContextMenuNames.modifyInRnaBuilder,
    title: "Modify in RNA Builder...",
    disabled: !(menuProps !== null && menuProps !== void 0 && menuProps.isSelectedOnlyNucleoelements) || menuProps.hasAntisense,
    hidden: function hidden(_ref8) {
      var props = _ref8.props;
      return !(props !== null && props !== void 0 && props.sequenceItemRenderer) || !(menuProps !== null && menuProps !== void 0 && menuProps.isSelectedAtLeastOneNucleoelement);
    }
  }, {
    name: SequenceItemContextMenuNames.modifyAminoAcids,
    title: "Modify amino acids",
    disabled: false,
    hidden: !modifyAminoAcidsMenuItems.length,
    subMenuItems: modifyAminoAcidsMenuItems,
    separator: true
  }, {
    name: SequenceItemContextMenuNames["delete"],
    title: "Delete",
    disabled: (selectedMonomers === null || selectedMonomers === void 0 ? void 0 : selectedMonomers.length) === 0,
    icon: jsx(Icon, {
      name: "deleteMenu"
    })
  }];
  var handleMenuChange = function handleMenuChange2(_ref9) {
    var _menuProps$selectedSe;
    var menuItemId = _ref9.id, props = _ref9.props;
    if (!editor) {
      return;
    }
    switch (true) {
      case menuItemId === SequenceItemContextMenuNames.modifyInRnaBuilder:
        editor.events.turnOnSequenceEditInRNABuilderMode.dispatch();
        dispatch2(setSelectedTabIndex2(LIBRARY_TAB_INDEX.RNA));
        dispatch2(setIsEditMode2(true));
        dispatch2(setActivePreset2({}));
        dispatch2(setActiveRnaBuilderItem2(null));
        if (menuProps !== null && menuProps !== void 0 && (_menuProps$selectedSe = menuProps.selectedSequenceLabeledNodes) !== null && _menuProps$selectedSe !== void 0 && _menuProps$selectedSe.length && menuProps !== null && menuProps !== void 0 && menuProps.title) {
          dispatch2(setSequenceSelectionName2(menuProps === null || menuProps === void 0 ? void 0 : menuProps.title));
          dispatch2(setSequenceSelection2(menuProps === null || menuProps === void 0 ? void 0 : menuProps.selectedSequenceLabeledNodes));
          dispatch2(setIsSequenceFirstsOnlyNucleoelementsSelected2(menuProps === null || menuProps === void 0 ? void 0 : menuProps.isSequenceFirstsOnlyNucleoelementsSelected));
        }
        break;
      case menuItemId === SequenceItemContextMenuNames.startNewSequence:
        editor.events.startNewSequence.dispatch(props.sequenceItemRenderer);
        break;
      case menuItemId === SequenceItemContextMenuNames.editSequence:
        editor.events.editSequence.dispatch(props.sequenceItemRenderer);
        break;
      case menuItemId === SequenceItemContextMenuNames.createRnaAntisenseStrand:
        editor.events.createAntisenseChain.dispatch(false);
        break;
      case menuItemId === SequenceItemContextMenuNames.createDnaAntisenseStrand:
        editor.events.createAntisenseChain.dispatch(true);
        break;
      case menuItemId === SequenceItemContextMenuNames.establishHydrogenBond:
        editor.events.establishHydrogenBond.dispatch(props.sequenceItemRenderer);
        break;
      case menuItemId === SequenceItemContextMenuNames.deleteHydrogenBond: {
        var _props$sequenceItemRe3;
        var sequenceViewModel = SequenceRenderer.sequenceViewModel;
        var monomerToChain = sequenceViewModel.chainsCollection.monomerToChain;
        var antisenseChainToSelectedNodeMap = /* @__PURE__ */ new Map();
        var selectedTwoStrandedNodes = selections !== null && selections !== void 0 && selections.length ? selections.reduce(function(acc, selectionRange) {
          return [].concat(_toConsumableArray(acc), _toConsumableArray(selectionRange));
        }, []).map(function(nodeSelection) {
          return nodeSelection.twoStrandedNode;
        }) : [(_props$sequenceItemRe3 = props.sequenceItemRenderer) === null || _props$sequenceItemRe3 === void 0 ? void 0 : _props$sequenceItemRe3.twoStrandedNode];
        selectedTwoStrandedNodes.forEach(function(selectedTwoStrandedNode) {
          if (selectedTwoStrandedNode.antisenseChain && selectedTwoStrandedNode.antisenseNode && !(selectedTwoStrandedNode.antisenseNode instanceof EmptySequenceNode || selectedTwoStrandedNode.antisenseNode instanceof BackBoneSequenceNode)) {
            if (!antisenseChainToSelectedNodeMap.has(selectedTwoStrandedNode.antisenseChain)) {
              antisenseChainToSelectedNodeMap.set(selectedTwoStrandedNode.antisenseChain, /* @__PURE__ */ new Set());
            }
            var antisenseChainSelectedNodes = antisenseChainToSelectedNodeMap.get(selectedTwoStrandedNode.antisenseChain);
            if (!antisenseChainSelectedNodes) {
              return;
            }
            antisenseChainSelectedNodes.add(selectedTwoStrandedNode);
          }
        });
        var isGoingToDeleteAllHydrogenBondsForAnyChain = false;
        antisenseChainToSelectedNodeMap.forEach(function(selectedTwoStrandedNodes2, chain) {
          var firstSelectedTwoStrandedNode = _toConsumableArray(selectedTwoStrandedNodes2.values())[0];
          var senseChain = firstSelectedTwoStrandedNode.chain;
          var selectedAntisenseNodes = new Set(_toConsumableArray(selectedTwoStrandedNodes2.values()).map(function(node) {
            return node.antisenseNode;
          }));
          var hasMoreHydrogenConnectionsThanSelected = chain.nodes.some(function(node) {
            return !selectedAntisenseNodes.has(node) && node.monomers.some(function(monomer) {
              return monomer.hydrogenBonds.some(function(hydrogenBond) {
                var anotherMonomer = hydrogenBond.getAnotherMonomer(monomer);
                var anotherChain = anotherMonomer && monomerToChain.get(anotherMonomer);
                return anotherChain === senseChain;
              });
            });
          });
          if (!hasMoreHydrogenConnectionsThanSelected) {
            isGoingToDeleteAllHydrogenBondsForAnyChain = true;
          }
        });
        if (isGoingToDeleteAllHydrogenBondsForAnyChain) {
          editor.events.openConfirmationDialog.dispatch({
            title: "Deletion of all Hydrogen Bonds",
            confirmationText: "Deleting all hydrogen bonds will cause the separation of two chains. Do you wish to proceed?",
            onConfirm: function onConfirm() {
              editor.events.deleteHydrogenBond.dispatch(props.sequenceItemRenderer);
            }
          });
        } else {
          editor.events.deleteHydrogenBond.dispatch(props.sequenceItemRenderer);
        }
        break;
      }
      case (menuItemId === null || menuItemId === void 0 ? void 0 : menuItemId.startsWith(AMINO_ACID_MODIFICATION_MENU_ITEM_PREFIX)): {
        var modificationType = menuItemId === null || menuItemId === void 0 ? void 0 : menuItemId.replace(AMINO_ACID_MODIFICATION_MENU_ITEM_PREFIX, "");
        editor.events.modifyAminoAcids.dispatch({
          monomers: monomersForAminoAcidModification,
          modificationType
        });
        break;
      }
      case menuItemId === "copy":
        editor.events.copySelectedStructure.dispatch();
        break;
      case menuItemId === "paste":
        editor.events.pasteFromClipboard.dispatch();
        break;
      case menuItemId === "delete":
        editor.events.deleteSelectedStructure.dispatch();
        break;
    }
  };
  var ketcherEditorRootElement = document.querySelector(KETCHER_MACROMOLECULES_ROOT_NODE_SELECTOR);
  return ketcherEditorRootElement && isSequenceMode && !isSequenceEditInRNABuilderMode ? reactDomExports.createPortal(jsx(ContextMenu, {
    id: CONTEXT_MENU_ID.FOR_SEQUENCE,
    handleMenuChange,
    menuItems
  }), ketcherEditorRootElement) : null;
};
var Container$1 = createStyled("div", {
  target: "e1amohl43"
} )("display:flex;flex-direction:column;align-items:start;gap:8px;overflow:hidden;width:", function(props) {
  return props.isLongName ? "450px" : "345px";
}, ";height:345px;background:", function(props) {
  return props.theme.ketcher.color.background.primary;
}, ";border:", function(props) {
  return props.theme.ketcher.border.regular;
}, ";border-radius:", function(props) {
  return props.theme.ketcher.border.radius.regular;
}, ";box-shadow:", function(props) {
  return props.theme.ketcher.shadow.regular;
}, ";" + ("" ));
var MonomerName = createStyled("p", {
  target: "e1amohl42"
} )("width:calc(100% - 16px);padding:8px;color:", function(props) {
  return props.theme.ketcher.color.text.primary;
}, ";background-color:#cceaee;font-size:", function(props) {
  return props.isLongName ? "8px" : props.theme.ketcher.font.size.regular;
}, ";font-weight:700;word-break:break-all;text-align:left;margin:0;white-space:pre-wrap;", function(props) {
  return props.isLongName && "\n    max-height: 200px;\n    overflow: hidden;\n    display: -webkit-box;\n    -webkit-line-clamp: 15;\n    -webkit-box-orient: vertical;\n  ";
}, ";" + ("" ));
var StyledStructRender = createStyled(StructRender, {
  target: "e1amohl41"
} )({
  name: "tqmz0h",
  styles: "flex:1 1 auto;min-height:80px;width:100%;padding:0 8px"
} );
var InfoBlock = createStyled("div", {
  target: "e1amohl40"
} )({
  name: "1i0z1wm",
  styles: "width:100%;display:flex;flex-shrink:0;gap:8px;padding:0 8px 4px"
} );
var useAttachmentPoints = function useAttachmentPoints2(_ref3) {
  var monomerCaps = _ref3.monomerCaps, attachmentPointsToBonds = _ref3.attachmentPointsToBonds;
  return reactExports.useMemo(function() {
    var preparedAttachmentPointsData = [];
    var connectedAttachmentPoints = [];
    if (!monomerCaps) {
      return {
        preparedAttachmentPointsData,
        connectedAttachmentPoints
      };
    }
    Object.entries(monomerCaps).forEach(function(_ref22) {
      var _ref32 = _slicedToArray(_ref22, 2), id2 = _ref32[0], label = _ref32[1];
      var connected = Boolean(attachmentPointsToBonds === null || attachmentPointsToBonds === void 0 ? void 0 : attachmentPointsToBonds[id2]);
      if (connected) {
        connectedAttachmentPoints.push(id2);
      }
      var preparedData = {
        id: id2,
        label: hydrateLeavingGroup$1(label),
        connected
      };
      preparedAttachmentPointsData.push(preparedData);
    });
    return {
      preparedAttachmentPointsData,
      connectedAttachmentPoints
    };
  }, [monomerCaps, attachmentPointsToBonds]);
};
var useIDTAliasesTextForMonomer = function useIDTAliasesTextForMonomer2(_ref3) {
  var idtAliases = _ref3.idtAliases, attachmentPointsToBonds = _ref3.attachmentPointsToBonds;
  return reactExports.useMemo(function() {
    if (!idtAliases) {
      return null;
    }
    var base = idtAliases.base, modifications = idtAliases.modifications;
    if (!modifications) {
      return removeSlashesFromIdtAlias(base);
    }
    var endpoint5 = modifications.endpoint5, internal = modifications.internal, endpoint3 = modifications.endpoint3;
    if (attachmentPointsToBonds) {
      var R1 = attachmentPointsToBonds.R1, R2 = attachmentPointsToBonds.R2;
      var hasR1Connection = R1 != null;
      var hasR2Connection = R2 != null;
      if (hasR1Connection && !hasR2Connection) {
        return removeSlashesFromIdtAlias(endpoint3 !== null && endpoint3 !== void 0 ? endpoint3 : internal);
      } else if (!hasR1Connection && hasR2Connection) {
        return removeSlashesFromIdtAlias(endpoint5 !== null && endpoint5 !== void 0 ? endpoint5 : internal);
      } else if (hasR1Connection && hasR2Connection) {
        var _ref22;
        return removeSlashesFromIdtAlias((_ref22 = internal !== null && internal !== void 0 ? internal : endpoint5) !== null && _ref22 !== void 0 ? _ref22 : endpoint3);
      } else {
        var _ref32;
        return removeSlashesFromIdtAlias((_ref32 = endpoint5 !== null && endpoint5 !== void 0 ? endpoint5 : internal) !== null && _ref32 !== void 0 ? _ref32 : endpoint3);
      }
    }
    var allModificationsHaveSameBase = Object.values(modifications).every(function(modification) {
      return modification.includes(base);
    });
    if (endpoint3 && endpoint5 && internal && allModificationsHaveSameBase) {
      return removeSlashesFromIdtAlias(base);
    }
    var baseToPositionsMap = {};
    Object.values(modifications).forEach(function(modification) {
      var _removeSlashesFromIdt;
      var cleanModification = (_removeSlashesFromIdt = removeSlashesFromIdtAlias(modification)) !== null && _removeSlashesFromIdt !== void 0 ? _removeSlashesFromIdt : "";
      var _ref4 = [cleanModification.charAt(0), cleanModification.slice(1)], position = _ref4[0], base2 = _ref4[1];
      baseToPositionsMap[base2] = baseToPositionsMap[base2] ? [].concat(_toConsumableArray(baseToPositionsMap[base2]), [position]) : [position];
    });
    return Object.entries(baseToPositionsMap).map(function(_ref5) {
      var _ref6 = _slicedToArray(_ref5, 2), base2 = _ref6[0], positions = _ref6[1];
      return "(".concat(positions.join(", "), ")").concat(base2);
    }).join(", ");
  }, [idtAliases, attachmentPointsToBonds]);
};
var useIDTAliasesTextForMonomer$1 = useIDTAliasesTextForMonomer;
var MonomerPreviewContainer = createStyled("span", {
  target: "epjjwrk3"
} )("width:max-content;max-width:100%;display:flex;flex-direction:column;align-items:flex-start;font-size:", function(props) {
  return props.theme.ketcher.font.size.regular;
}, ";font-weight:500;line-height:normal;color:", function(props) {
  return props.theme.ketcher.color.text.lightgrey;
}, ";padding-left:", function(_ref3) {
  var preset = _ref3.preset;
  return preset ? "0" : "8px";
}, ";border-left:", function(_ref22) {
  var preset = _ref22.preset;
  return preset ? "none" : "1px solid #D9DCEA";
}, ";" + ("" ));
var MonomerPreviewText = createStyled("p", {
  target: "epjjwrk2"
} )({
  name: "ti75j2",
  styles: "margin:0"
} );
var MonomerPreviewTitle = createStyled("span", {
  target: "epjjwrk1"
} )({
  name: "3myie7",
  styles: "color:#7c7c7c;margin-right:4px"
} );
var MonomerPreviewList = createStyled("span", {
  target: "epjjwrk0"
} )({
  name: "9ig07c",
  styles: "color:#585858;white-space:normal;overflow-wrap:anywhere;word-break:break-word"
} );
var stripSquareBrackets = function stripSquareBrackets2(text) {
  return text.replace(/\[|\]/g, "");
};
function MonomerPreviewProperties(_ref3) {
  var idtAliasesText = _ref3.idtAliasesText, axoLabsText = _ref3.axoLabsText, helmText = _ref3.helmText, bilnText = _ref3.bilnText, modificationTypeText = _ref3.modificationTypeText, preset = _ref3.preset;
  var rows = [].concat(_toConsumableArray(idtAliasesText ? [{
    label: "IDT",
    text: idtAliasesText
  }] : []), _toConsumableArray(axoLabsText ? [{
    label: "AxoLabs",
    text: axoLabsText
  }] : []), _toConsumableArray(helmText ? [{
    label: "HELM",
    text: stripSquareBrackets(helmText)
  }] : []), _toConsumableArray(bilnText ? [{
    label: "BILN",
    text: stripSquareBrackets(bilnText)
  }] : []), _toConsumableArray(modificationTypeText ? [{
    label: "Modification type",
    text: modificationTypeText
  }] : []));
  if (!rows.length) return null;
  return jsx(MonomerPreviewContainer, {
    preset,
    children: rows.map(function(item) {
      return jsxs(MonomerPreviewText, {
        children: [jsxs(MonomerPreviewTitle, {
          children: [item.label, ":"]
        }), jsx(MonomerPreviewList, {
          children: item.text
        })]
      }, item.label);
    })
  });
}
var AttachmentPointsList = createStyled("div", {
  target: "e112ss7f3"
} )({
  name: "1m2mukt",
  styles: "flex:1;display:flex;align-items:center;flex-wrap:wrap;gap:8px;font-size:12px;line-height:14px"
} );
var AttachmentPoint$1 = createStyled("div", {
  target: "e112ss7f2"
} )("display:flex;align-items:center;gap:2px;border-radius:4px;background-color:", function(_ref3) {
  var connected = _ref3.connected;
  return connected ? "#E1E5EA" : "transparent";
}, ";padding:", function(_ref22) {
  var connected = _ref22.connected;
  return connected ? "4px" : "0";
}, ";color:", function(_ref3) {
  var connected = _ref3.connected;
  return connected ? "#8A8B8E" : "inherit";
}, ";" + ("" ));
var AttachmentPointID = createStyled("span", {
  target: "e112ss7f1"
} )({
  name: "f3vz0n",
  styles: "font-weight:500"
} );
var AttachmentPointLabel = createStyled("span", {
  target: "e112ss7f0"
} )({
  name: "16ceglb",
  styles: "font-weight:600"
} );
var AttachmentPoints = function AttachmentPoints2(_ref3) {
  var preparedAttachmentPointsData = _ref3.preparedAttachmentPointsData;
  if (!preparedAttachmentPointsData.length) {
    return null;
  }
  return jsx(AttachmentPointsList, {
    children: preparedAttachmentPointsData.map(function(_ref22) {
      var id2 = _ref22.id, connected = _ref22.connected, label = _ref22.label;
      return jsxs(AttachmentPoint$1, {
        connected,
        children: [jsxs(AttachmentPointID, {
          children: [id2, !connected && ":"]
        }), !connected && jsx(AttachmentPointLabel, {
          children: label
        })]
      }, id2);
    })
  });
};
var AttachmentPoints$1 = AttachmentPoints;
var MonomerPreview = function MonomerPreview2(_ref3) {
  var _monomer$struct;
  var className = _ref3.className;
  var preview2 = useAppSelector(selectShowPreview);
  var LONG_NAME_THRESHOLD = 100;
  var monomer = preview2.monomer, attachmentPointsToBonds = preview2.attachmentPointsToBonds;
  var idtAliases = monomer === null || monomer === void 0 ? void 0 : monomer.props.idtAliases;
  var axoLabsAlias = monomer === null || monomer === void 0 ? void 0 : monomer.props.aliasAxoLabs;
  var aliasHelm = monomer === null || monomer === void 0 ? void 0 : monomer.props.aliasHELM;
  var aliasBiln = monomer === null || monomer === void 0 ? void 0 : monomer.props.aliasBILN;
  var modificationTypes = monomer === null || monomer === void 0 ? void 0 : monomer.props.modificationTypes;
  var _useAttachmentPoints = useAttachmentPoints({
    monomerCaps: monomer === null || monomer === void 0 ? void 0 : monomer.props.MonomerCaps,
    attachmentPointsToBonds
  }), preparedAttachmentPointsData = _useAttachmentPoints.preparedAttachmentPointsData, connectedAttachmentPoints = _useAttachmentPoints.connectedAttachmentPoints;
  var idtAliasesText = useIDTAliasesTextForMonomer$1({
    idtAliases,
    attachmentPointsToBonds
  });
  if (!monomer) {
    return null;
  }
  var isUnresolved = monomer.props.unresolved;
  var monomerName = isUnresolved ? monomer.label : ((_monomer$struct = monomer.struct) === null || _monomer$struct === void 0 ? void 0 : _monomer$struct.name) || monomer.label;
  var isMonomerPreviewPropertiesVisible = idtAliasesText || axoLabsAlias || aliasHelm || aliasBiln || modificationTypes;
  return (monomer.struct || isUnresolved) && jsxs(Container$1, {
    className,
    isLongName: monomerName.length > LONG_NAME_THRESHOLD,
    "data-testid": "polymer-library-preview",
    "data-idtaliases": idtAliasesText !== null && idtAliasesText !== void 0 ? idtAliasesText : void 0,
    "data-axolabs": axoLabsAlias !== null && axoLabsAlias !== void 0 ? axoLabsAlias : void 0,
    "data-helm": aliasHelm !== null && aliasHelm !== void 0 ? aliasHelm : void 0,
    "data-biln": aliasBiln !== null && aliasBiln !== void 0 ? aliasBiln : void 0,
    "data-modificationtype": getModificationTypeAttribute(modificationTypes),
    children: [monomerName.length > 0 && jsx(MonomerName, {
      "data-testid": "preview-tooltip-title",
      isLongName: monomerName.length > 100,
      children: monomerName
    }), isUnresolved ? jsx(UnresolvedMonomerPreview$1, {}) : jsx(StyledStructRender, {
      struct: monomer.struct,
      options: {
        connectedMonomerAttachmentPoints: connectedAttachmentPoints,
        usageInMacromolecule: UsageInMacromolecule.MonomerPreview,
        labelInPreview: true,
        needCache: false
      }
    }), jsxs(InfoBlock, {
      children: [jsx(AttachmentPoints$1, {
        preparedAttachmentPointsData
      }), isMonomerPreviewPropertiesVisible && jsx(MonomerPreviewProperties, {
        idtAliasesText: idtAliasesText !== null && idtAliasesText !== void 0 ? idtAliasesText : void 0,
        axoLabsText: axoLabsAlias !== null && axoLabsAlias !== void 0 ? axoLabsAlias : void 0,
        helmText: aliasHelm !== null && aliasHelm !== void 0 ? aliasHelm : void 0,
        bilnText: aliasBiln !== null && aliasBiln !== void 0 ? aliasBiln : void 0,
        modificationTypeText: Array.isArray(modificationTypes) ? modificationTypes.join(", ") : modificationTypes
      })]
    })]
  });
};
var MonomerPreview$1 = MonomerPreview;
var PresetContainer = createStyled("div", {
  target: "ec5fs977"
} )("display:flex;flex-direction:column;align-items:center;gap:8px;padding:8px;background:", function(props) {
  return props.theme.ketcher.color.background.primary;
}, ";border:", function(props) {
  return props.theme.ketcher.border.regular;
}, ";border-radius:", function(props) {
  return props.theme.ketcher.border.radius.regular;
}, ";box-shadow:", function(props) {
  return props.theme.ketcher.shadow.regular;
}, ";" + ("" ));
var PresetMonomerRow = createStyled("div", {
  target: "ec5fs976"
} )({
  name: "s5xdrg",
  styles: "display:flex;align-items:center"
} );
var PresetMonomerLabel = createStyled("div", {
  target: "ec5fs975"
} )("font-size:", function(props) {
  return props.theme.ketcher.font.size.regular;
}, ";line-height:", function(props) {
  return props.theme.ketcher.font.size.regular;
}, ";font-weight:600;padding-right:2px;" + ("" ));
var PresetMonomerName = createStyled("div", {
  target: "ec5fs974"
} )("color:", function(props) {
  return props.theme.ketcher.color.text.lightgrey;
}, ";font-size:", function(props) {
  return props.theme.ketcher.font.size.regular;
}, ";font-weight:400;white-space:nowrap;" + ("" ));
var PresetName = createStyled("p", {
  target: "ec5fs973"
} )("color:", function(props) {
  return props.theme.ketcher.color.text.primary;
}, ";font-size:", function(props) {
  return props.theme.ketcher.font.size.regular;
}, ";font-weight:700;word-break:break-all;text-align:center;margin-top:0;margin-bottom:8px;" + ("" ));
var PresetIcon = createStyled(Icon, {
  target: "ec5fs972"
} )("height:14px;width:14px;margin-right:4px;color:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.color.icon.grey;
}, ";stroke:", function(_ref22) {
  var theme = _ref22.theme;
  return theme.ketcher.color.icon.grey;
}, ";" + ("" ));
var PhosphatePositionIcon = createStyled(Icon, {
  target: "ec5fs971"
} )({
  name: "1j379ef",
  styles: "height:15px;width:15px;flex-shrink:0"
} );
var PhosphatePositionIconWrapper = createStyled("span", {
  target: "ec5fs970"
} )({
  name: "1ag7b4g",
  styles: "display:inline-flex;align-items:center;margin-left:6px"
} );
var useIDTAliasesTextForPreset = function useIDTAliasesTextForPreset2(_ref3) {
  var presetName = _ref3.presetName, position = _ref3.position, idtAliases = _ref3.idtAliases;
  return reactExports.useMemo(function() {
    if (!presetName || !idtAliases) {
      return null;
    }
    if (presetName.includes("MOE")) {
      var _removeSlashesFromIdt, _removeSlashesFromIdt2, _removeSlashesFromIdt3;
      var base = idtAliases.base, modifications = idtAliases.modifications;
      var endpoint5 = (_removeSlashesFromIdt = removeSlashesFromIdtAlias(modifications === null || modifications === void 0 ? void 0 : modifications.endpoint5)) !== null && _removeSlashesFromIdt !== void 0 ? _removeSlashesFromIdt : "5".concat(base);
      var internal = (_removeSlashesFromIdt2 = removeSlashesFromIdtAlias(modifications === null || modifications === void 0 ? void 0 : modifications.internal)) !== null && _removeSlashesFromIdt2 !== void 0 ? _removeSlashesFromIdt2 : "i".concat(base);
      var endpoint3 = (_removeSlashesFromIdt3 = removeSlashesFromIdtAlias(modifications === null || modifications === void 0 ? void 0 : modifications.endpoint3)) !== null && _removeSlashesFromIdt3 !== void 0 ? _removeSlashesFromIdt3 : "3".concat(base);
      switch (position) {
        case PresetPosition.Library: {
          var isAllPositionsHaveSameBase = [endpoint5, internal, endpoint3].every(function(alias) {
            return alias.includes(base);
          });
          if (isAllPositionsHaveSameBase) {
            return base;
          }
          return "".concat(endpoint5, ", ").concat(internal);
        }
        case PresetPosition.ChainStart:
          return endpoint5;
        case PresetPosition.ChainMiddle:
          return internal;
        case PresetPosition.ChainEnd:
          return endpoint3;
      }
    }
    return removeSlashesFromIdtAlias(idtAliases.base);
  }, [presetName, position, idtAliases]);
};
var useIDTAliasesTextForPreset$1 = useIDTAliasesTextForPreset;
var getIconNameForMonomer = function getIconNameForMonomer2(monomer) {
  switch (monomer.props.MonomerClass) {
    case KetMonomerClass.Sugar:
      return "sugar";
    case KetMonomerClass.Base:
      return "base";
    case KetMonomerClass.Phosphate:
      return "phosphate";
    default:
      return "chem";
  }
};
var PHOSPHATE_INDEX = 2;
var PresetPreview = function PresetPreview2(_ref3) {
  var className = _ref3.className;
  var preview2 = useAppSelector(selectShowPreview);
  var monomers = preview2.monomers, name = preview2.name, position = preview2.position, idtAliases = preview2.idtAliases, aliasAxoLabs = preview2.aliasAxoLabs;
  var _monomers = _slicedToArray(monomers, 2), baseMonomer = _monomers[1];
  var presetName = name !== null && name !== void 0 ? name : baseMonomer === null || baseMonomer === void 0 ? void 0 : baseMonomer.props.Name;
  var axoLabsText = aliasAxoLabs !== null && aliasAxoLabs !== void 0 ? aliasAxoLabs : baseMonomer === null || baseMonomer === void 0 ? void 0 : baseMonomer.props.aliasAxoLabs;
  var idtAliasesText = useIDTAliasesTextForPreset$1({
    presetName,
    position,
    idtAliases
  });
  var isMonomerPreviewPropertiesVisible = idtAliasesText || axoLabsText;
  var phosphatePositionIconName;
  if (preview2.phosphatePosition === "left") {
    phosphatePositionIconName = "preset-left-phosphate";
  } else {
    phosphatePositionIconName = preview2.phosphatePosition === "right" ? "preset-right-phosphate" : void 0;
  }
  var phosphatePositionTooltip;
  if (preview2.phosphatePosition === "left") {
    phosphatePositionTooltip = "Phosphate on the left (5')";
  } else {
    phosphatePositionTooltip = preview2.phosphatePosition === "right" ? "Phosphate on the right (3')" : void 0;
  }
  var getMonomerNameText = function getMonomerNameText2(monomer) {
    return "(".concat(monomer.props.Name, ")");
  };
  return jsxs(PresetContainer, {
    className,
    style: {
      alignItems: "flex-start"
    },
    "data-testid": "polymer-library-preview",
    "data-idtaliases": idtAliasesText !== null && idtAliasesText !== void 0 ? idtAliasesText : void 0,
    "data-axolabs": axoLabsText !== null && axoLabsText !== void 0 ? axoLabsText : void 0,
    children: [jsx(PresetName, {
      "data-testid": "preview-tooltip-title",
      children: presetName
    }), monomers.map(function(monomer, index) {
      var _monomer$props$id;
      return monomer ? jsxs(PresetMonomerRow, {
        children: [jsx(PresetIcon, {
          name: getIconNameForMonomer(monomer)
        }), jsx(PresetMonomerLabel, {
          children: monomer.label
        }), jsx(PresetMonomerName, {
          children: getMonomerNameText(monomer)
        }), index === PHOSPHATE_INDEX && phosphatePositionIconName && jsx(PhosphatePositionIconWrapper, {
          title: phosphatePositionTooltip,
          "data-testid": "preset-preview-phosphate-position-icon",
          "data-phosphate-position": preview2.phosphatePosition,
          children: jsx(PhosphatePositionIcon, {
            name: phosphatePositionIconName
          })
        })]
      }, (_monomer$props$id = monomer.props.id) !== null && _monomer$props$id !== void 0 ? _monomer$props$id : index) : null;
    }), isMonomerPreviewPropertiesVisible && jsx(MonomerPreviewProperties, {
      preset: true,
      idtAliasesText: idtAliasesText !== null && idtAliasesText !== void 0 ? idtAliasesText : void 0,
      axoLabsText
    })]
  });
};
var PresetStyledPreview = createStyled(PresetPreview, {
  target: "e1wupxfd0"
} )("" );
var PresetPreview$1 = PresetStyledPreview;
var Container = createStyled("div", {
  target: "envzkt90"
} )("display:flex;flex-direction:column;align-items:start;gap:8px;background:", function(props) {
  return props.theme.ketcher.color.background.primary;
}, ";border:", function(props) {
  return props.theme.ketcher.border.regular;
}, ";border-radius:", function(props) {
  return props.theme.ketcher.border.radius.regular;
}, ";box-shadow:", function(props) {
  return props.theme.ketcher.shadow.regular;
}, ";" + ("" ));
var AttachmentPoint = createStyled("div", {
  target: "e1m0yzrp2"
} )(function(_ref3) {
  var connected = _ref3.connected, inBond = _ref3.inBond, theme = _ref3.theme;
  return {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "2px",
    color: inBond || !connected ? theme.ketcher.color.text.primary : "#B4B9D6"
  };
}, "" );
var AttachmentPointName = createStyled("p", {
  target: "e1m0yzrp1"
} )(function(_ref22) {
  var theme = _ref22.theme;
  return {
    margin: 0,
    fontSize: theme.ketcher.font.size.small,
    lineHeight: "12px"
  };
}, "" );
var LeavingGroup = createStyled("p", {
  target: "e1m0yzrp0"
} )(function(_ref3) {
  var inBond = _ref3.inBond, theme = _ref3.theme;
  return {
    margin: 0,
    padding: "4px",
    fontWeight: theme.ketcher.font.weight.bold,
    lineHeight: "14px",
    borderRadius: "4px",
    backgroundColor: inBond ? "#CDF1FC" : "transparent"
  };
}, "" );
var BondAttachmentPoints = function BondAttachmentPoints2(_ref3) {
  var attachmentPoints = _ref3.attachmentPoints, attachmentPointInBond = _ref3.attachmentPointInBond;
  return jsx(Fragment, {
    children: attachmentPoints.map(function(attachmentPoint) {
      return jsxs(AttachmentPoint, {
        connected: attachmentPoint.connected,
        inBond: attachmentPoint.id === attachmentPointInBond,
        children: [jsx(AttachmentPointName, {
          children: attachmentPoint.id
        }), jsx(LeavingGroup, {
          inBond: attachmentPoint.id === attachmentPointInBond,
          children: attachmentPoint.label
        })]
      }, attachmentPoint.id);
    })
  });
};
var BondAttachmentPoints$1 = BondAttachmentPoints;
var BondPreview = function BondPreview2(_ref3) {
  var className = _ref3.className;
  var preview2 = useAppSelector(selectShowPreview);
  var polymerBond = preview2.polymerBond, style = preview2.style;
  var ContainerDynamic = reactExports.useMemo(function() {
    var _style$top, _style$left, _style$right;
    if (!style) {
      return createStyled(Container, {
        target: "e18hk05c2"
      } )("" );
    }
    return createStyled(Container, {
      target: "e18hk05c1"
    } )("top:", (_style$top = style === null || style === void 0 ? void 0 : style.top) !== null && _style$top !== void 0 ? _style$top : "", ";left:", (_style$left = style === null || style === void 0 ? void 0 : style.left) !== null && _style$left !== void 0 ? _style$left : "", ";right:", (_style$right = style === null || style === void 0 ? void 0 : style.right) !== null && _style$right !== void 0 ? _style$right : "", ";" + ("" ));
  }, [style]);
  var firstMonomer = polymerBond.firstMonomer, secondMonomer = polymerBond.secondMonomer, firstMonomerAttachmentPoint = polymerBond.firstMonomerAttachmentPoint, secondMonomerAttachmentPoint = polymerBond.secondMonomerAttachmentPoint;
  var _useAttachmentPoints = useAttachmentPoints({
    monomerCaps: firstMonomer.monomerCaps,
    attachmentPointsToBonds: firstMonomer.attachmentPointsToBonds
  }), firstMonomerPreparedAPsData = _useAttachmentPoints.preparedAttachmentPointsData, firstMonomerConnectedAPs = _useAttachmentPoints.connectedAttachmentPoints;
  var _useAttachmentPoints2 = useAttachmentPoints({
    monomerCaps: secondMonomer === null || secondMonomer === void 0 ? void 0 : secondMonomer.monomerCaps,
    attachmentPointsToBonds: secondMonomer === null || secondMonomer === void 0 ? void 0 : secondMonomer.attachmentPointsToBonds
  }), secondMonomerPreparedAPsData = _useAttachmentPoints2.preparedAttachmentPointsData, secondMonomerConnectedAPs = _useAttachmentPoints2.connectedAttachmentPoints;
  if (!firstMonomer || !secondMonomer) {
    return null;
  }
  return jsx(ContainerDynamic, {
    className,
    "data-testid": "polymer-library-preview",
    children: jsx(ConnectionOverview$1, {
      firstMonomer,
      secondMonomer,
      firstMonomerOverview: jsx(MonomerOverview$1, {
        monomer: firstMonomer,
        usage: UsageInMacromolecule.BondPreview,
        connectedAttachmentPoints: firstMonomerConnectedAPs,
        selectedAttachmentPoint: firstMonomerAttachmentPoint,
        attachmentPoints: jsx(BondAttachmentPoints$1, {
          attachmentPoints: firstMonomerPreparedAPsData,
          attachmentPointInBond: firstMonomerAttachmentPoint
        })
      }),
      secondMonomerOverview: jsx(MonomerOverview$1, {
        monomer: secondMonomer,
        usage: UsageInMacromolecule.BondPreview,
        connectedAttachmentPoints: secondMonomerConnectedAPs,
        selectedAttachmentPoint: secondMonomerAttachmentPoint,
        attachmentPoints: jsx(BondAttachmentPoints$1, {
          attachmentPoints: secondMonomerPreparedAPsData,
          attachmentPointInBond: secondMonomerAttachmentPoint
        })
      })
    })
  });
};
var StyledPreview = createStyled(BondPreview, {
  target: "e18hk05c0"
} )("width:", preview.widthForBond, "px;height:", preview.heightForBond, "px;" + ("" ));
var BondPreview$1 = StyledPreview;
function ownKeys$4(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$4(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$4(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$4(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var PreviewContainer = createStyled("div", {
  target: "e88xzqx0"
} )("display:inline-block;position:absolute;background:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.color.background.primary;
}, ";z-index:", function(_ref22) {
  var theme = _ref22.theme;
  return theme.ketcher.zIndex.overlay;
}, ";" + ("" ));
var Preview = function Preview2() {
  var preview2 = useAppSelector(selectShowPreview);
  var previewRef = reactExports.useRef(null);
  var _useState = reactExports.useState(false), _useState2 = _slicedToArray(_useState, 2), isPreviewVisible = _useState2[0], setIsPreviewVisible = _useState2[1];
  var editor = useSelector(selectEditor);
  reactExports.useEffect(function() {
    if (!previewRef.current || preview2.style) {
      return;
    }
    if (preview2 !== null && preview2 !== void 0 && preview2.type) {
      var _previewRef$current, _ZoomTool$instance, _preview$target;
      previewRef.current.setAttribute("style", "");
      setIsPreviewVisible(true);
      var PREVIEW_OFFSET = 5;
      var previewBoundingClientRect = (_previewRef$current = previewRef.current) === null || _previewRef$current === void 0 ? void 0 : _previewRef$current.getBoundingClientRect();
      var previewHeight = (previewBoundingClientRect === null || previewBoundingClientRect === void 0 ? void 0 : previewBoundingClientRect.height) || 0;
      var previewWidth = (previewBoundingClientRect === null || previewBoundingClientRect === void 0 ? void 0 : previewBoundingClientRect.width) || 0;
      var canvasWrapperBoundingClientRect = (_ZoomTool$instance = ZoomTool.instance) === null || _ZoomTool$instance === void 0 || (_ZoomTool$instance = _ZoomTool$instance.canvasWrapper.node()) === null || _ZoomTool$instance === void 0 ? void 0 : _ZoomTool$instance.getBoundingClientRect();
      var canvasWrapperTop = (canvasWrapperBoundingClientRect === null || canvasWrapperBoundingClientRect === void 0 ? void 0 : canvasWrapperBoundingClientRect.top) || 0;
      var canvasWrapperBottom = (canvasWrapperBoundingClientRect === null || canvasWrapperBoundingClientRect === void 0 ? void 0 : canvasWrapperBoundingClientRect.bottom) || 0;
      var canvasWrapperLeft = (canvasWrapperBoundingClientRect === null || canvasWrapperBoundingClientRect === void 0 ? void 0 : canvasWrapperBoundingClientRect.left) || 0;
      var canvasWrapperRight = (canvasWrapperBoundingClientRect === null || canvasWrapperBoundingClientRect === void 0 ? void 0 : canvasWrapperBoundingClientRect.right) || 0;
      var targetBoundingClientRect = (_preview$target = preview2.target) === null || _preview$target === void 0 ? void 0 : _preview$target.getBoundingClientRect();
      var targetTop = (targetBoundingClientRect === null || targetBoundingClientRect === void 0 ? void 0 : targetBoundingClientRect.top) || 0;
      var targetBottom = (targetBoundingClientRect === null || targetBoundingClientRect === void 0 ? void 0 : targetBoundingClientRect.bottom) || 0;
      var targetLeft = (targetBoundingClientRect === null || targetBoundingClientRect === void 0 ? void 0 : targetBoundingClientRect.left) || 0;
      var targetWidth = (targetBoundingClientRect === null || targetBoundingClientRect === void 0 ? void 0 : targetBoundingClientRect.width) || 0;
      var targetCenterX = targetLeft - targetWidth / 2;
      var ketcherRootRect = editor === null || editor === void 0 ? void 0 : editor.ketcherRootElementBoundingClientRect;
      var ketcherRootOffsetX = (ketcherRootRect === null || ketcherRootRect === void 0 ? void 0 : ketcherRootRect.x) || 0;
      var ketcherRootOffsetY = (ketcherRootRect === null || ketcherRootRect === void 0 ? void 0 : ketcherRootRect.y) || 0;
      var topPreviewPosition = targetTop - previewHeight - PREVIEW_OFFSET - ketcherRootOffsetY;
      var bottomPreviewPosition = targetBottom + PREVIEW_OFFSET - ketcherRootOffsetY;
      var leftPreviewPosition = targetLeft + targetWidth / 2 - previewWidth / 2 - ketcherRootOffsetX;
      if (targetTop - previewHeight - PREVIEW_OFFSET >= canvasWrapperTop) {
        previewRef.current.style.top = "".concat(topPreviewPosition, "px");
      } else if (targetBottom + previewHeight > canvasWrapperBottom && targetBottom > canvasWrapperBottom / 2) {
        previewRef.current.style.top = "".concat(topPreviewPosition, "px");
      } else {
        previewRef.current.style.top = "".concat(bottomPreviewPosition, "px");
      }
      if (targetCenterX > previewWidth / 2 && targetCenterX + previewWidth / 2 < canvasWrapperRight) {
        previewRef.current.style.left = "".concat(leftPreviewPosition, "px");
      } else if (targetCenterX < previewWidth / 2) {
        previewRef.current.style.left = "".concat(canvasWrapperLeft, "px");
      } else {
        var SCROLL_BAR_OFFSET = 10;
        previewRef.current.style.left = "".concat(canvasWrapperRight - previewWidth - SCROLL_BAR_OFFSET, "px");
      }
    } else if (isPreviewVisible) {
      setIsPreviewVisible(false);
      previewRef.current.setAttribute("style", "");
    }
  }, [preview2]);
  if (!preview2) {
    return null;
  }
  return jsxs(PreviewContainer, {
    ref: previewRef,
    style: _objectSpread$4({}, preview2 === null || preview2 === void 0 ? void 0 : preview2.style),
    children: [preview2.type === PreviewType.Monomer && jsx(MonomerPreview$1, {}), preview2.type === PreviewType.Preset && jsx(PresetPreview$1, {}), preview2.type === PreviewType.Bond && jsx(BondPreview$1, {}), preview2.type === PreviewType.AmbiguousMonomer && jsx(AmbiguousMonomerPreview, {
      preview: preview2
    })]
  });
};
var SequenceTypeButton = createStyled(Button$1, {
  target: "e1brfei30"
} )(function(_ref3) {
  var theme = _ref3.theme, variant = _ref3.variant;
  return {
    color: variant === "outlined" ? theme.ketcher.color.text.primary : theme.ketcher.color.button.text.primary,
    boxShadow: "none",
    transition: "none",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    cursor: "pointer",
    padding: "4px 8px",
    border: variant === "outlined" ? theme.ketcher.outline.small : "none",
    background: variant === "outlined" ? theme.ketcher.color.background.primary : theme.ketcher.color.button.group.active,
    borderRadius: theme.ketcher.border.radius.regular,
    textTransform: "none",
    fontSize: theme.ketcher.font.size.regular,
    fontWeight: theme.ketcher.font.weight.regular,
    ":hover": {
      color: variant === "outlined" ? theme.ketcher.color.text.dark : theme.ketcher.color.button.text.primary,
      background: variant === "outlined" ? theme.ketcher.color.background.primary : theme.ketcher.color.button.group.hover,
      boxShadow: "none"
    },
    ":disabled": {
      cursor: "auto",
      background: "#e1e5ea",
      outline: "none"
    }
  };
}, "" );
var SequenceTypeGroupButton = function SequenceTypeGroupButton2() {
  var editor = useAppSelector(selectEditor);
  var _useState = reactExports.useState(editor === null || editor === void 0 ? void 0 : editor.events.changeSequenceTypeEnterMode), _useState2 = _slicedToArray(_useState, 2), activeSequenceType = _useState2[0], setActiveSequenceType = _useState2[1];
  var _useState3 = reactExports.useState(false), _useState4 = _slicedToArray(_useState3, 2), isSequenceMode = _useState4[0], setIsSequenceMode = _useState4[1];
  var isSequenceEditInRNABuilderMode = useAppSelector(selectIsSequenceEditInRNABuilderMode);
  var layoutMode = useLayoutMode();
  var isDisabled = !!isSequenceEditInRNABuilderMode;
  var dispatch2 = useAppDispatch();
  var onToggleSequenceMode = function onToggleSequenceMode2(data) {
    var mode = _typeof(data) === "object" ? data.mode : data;
    setIsSequenceMode(mode === "sequence-layout-mode");
  };
  reactExports.useEffect(function() {
    editor === null || editor === void 0 || editor.events.selectMode.add(onToggleSequenceMode);
    editor === null || editor === void 0 || editor.events.changeSequenceTypeEnterMode.add(function(mode) {
      dispatch2(setSelectedTabIndex2(mode === MONOMER_TYPES.PEPTIDE ? LIBRARY_TAB_INDEX.PEPTIDES : LIBRARY_TAB_INDEX.RNA));
      setActiveSequenceType(mode);
    });
    editor === null || editor === void 0 || editor.events.changeSequenceTypeEnterMode.dispatch(SequenceType.RNA);
    return function() {
      editor === null || editor === void 0 || editor.events.selectMode.remove(onToggleSequenceMode);
    };
  }, [editor]);
  reactExports.useEffect(function() {
    onToggleSequenceMode(layoutMode);
  }, [layoutMode]);
  var handleSelectSequenceType = function handleSelectSequenceType2(sequenceType) {
    editor === null || editor === void 0 || editor.events.changeSequenceTypeEnterMode.dispatch(sequenceType);
  };
  return isSequenceMode ? jsx(Box, {
    sx: {
      mr: 1,
      ml: 1
    },
    children: jsxs(ButtonGroup, {
      disabled: isDisabled,
      children: [jsx(SequenceTypeButton, {
        "data-testid": "".concat(SequenceType.RNA, "Btn"),
        title: "RNA (Ctrl+Alt+R)",
        variant: activeSequenceType === SequenceType.RNA ? "contained" : "outlined",
        onClick: function onClick() {
          return handleSelectSequenceType(SequenceType.RNA);
        },
        children: "RNA"
      }), jsx(SequenceTypeButton, {
        "data-testid": "".concat(SequenceType.DNA, "Btn"),
        title: "DNA (Ctrl+Alt+D)",
        variant: activeSequenceType === SequenceType.DNA ? "contained" : "outlined",
        onClick: function onClick() {
          return handleSelectSequenceType(SequenceType.DNA);
        },
        children: "DNA"
      }), jsx(SequenceTypeButton, {
        "data-testid": "".concat(SequenceType.PEPTIDE, "Btn"),
        title: "Peptides (Ctrl+Alt+P)",
        variant: activeSequenceType === SequenceType.PEPTIDE ? "contained" : "outlined",
        onClick: function onClick() {
          return handleSelectSequenceType(SequenceType.PEPTIDE);
        },
        children: "PEP"
      })]
    })
  }) : null;
};
var useRecalculateMacromoleculeProperties = function useRecalculateMacromoleculeProperties2() {
  var dispatch2 = useAppDispatch();
  var editor = useAppSelector(selectEditor);
  var unipositiveIonsMeasurementUnit = useAppSelector(selectUnipositiveIonsMeasurementUnit);
  var oligonucleotidesMeasurementUnit = useAppSelector(selectOligonucleotidesMeasurementUnit);
  var unipositiveIonsValue = useAppSelector(selectUnipositiveIonsValue);
  var oligonucleotidesValue = useAppSelector(selectOligonucleotidesValue);
  return (function() {
    var _ref3 = _asyncToGenerator(_regeneratorRuntime.mark(function _callee(shouldSkip) {
      var _chainsCollection$fir;
      var indigo, selectionDrawingEntitiesManager, ketSerializer, hasNoSelection, drawingEntitiesManagerToCalculateProperties, chainsCollection, firstMonomer, areAllMonomersConnectedByCovalentOrHydrogenBonds, hasNoChainsButMultipleFragments, serializedKet, calculateMacromoleculePropertiesResponse, macromoleculeProperties;
      return _regeneratorRuntime.wrap(function _callee$(_context) {
        while (1) switch (_context.prev = _context.next) {
          case 0:
            if (!(!editor || shouldSkip)) {
              _context.next = 2;
              break;
            }
            return _context.abrupt("return");
          case 2:
            indigo = IndigoProvider.getIndigo();
            selectionDrawingEntitiesManager = editor.drawingEntitiesManager.filterSelection();
            ketSerializer = new KetSerializer();
            hasNoSelection = !selectionDrawingEntitiesManager.hasDrawingEntities;
            drawingEntitiesManagerToCalculateProperties = selectionDrawingEntitiesManager.hasDrawingEntities ? selectionDrawingEntitiesManager : editor.drawingEntitiesManager;
            chainsCollection = ChainsCollection.fromMonomers(_toConsumableArray(drawingEntitiesManagerToCalculateProperties.monomers.values()));
            firstMonomer = (_chainsCollection$fir = chainsCollection.firstNode) === null || _chainsCollection$fir === void 0 ? void 0 : _chainsCollection$fir.monomer;
            areAllMonomersConnectedByCovalentOrHydrogenBonds = !firstMonomer || chainsCollection.chains.reduce(function(acc, chain) {
              return acc + chain.monomers.length;
            }, 0) <= getAllConnectedMonomersRecursively(firstMonomer).length;
            hasNoChainsButMultipleFragments = chainsCollection.chains.length === 0 && _toConsumableArray(drawingEntitiesManagerToCalculateProperties.monomers.values()).filter(function(monomer) {
              return monomer.monomerItem.props.isMicromoleculeFragment;
            }).length > 1;
            if (!(!drawingEntitiesManagerToCalculateProperties.hasDrawingEntities || !areAllMonomersConnectedByCovalentOrHydrogenBonds || hasNoSelection && hasNoChainsButMultipleFragments)) {
              _context.next = 14;
              break;
            }
            dispatch2(setMacromoleculesProperties2(void 0));
            return _context.abrupt("return");
          case 14:
            serializedKet = ketSerializer.serialize(new Struct(), editor.drawingEntitiesManager, void 0, false, true);
            _context.next = 17;
            return indigo.calculateMacromoleculeProperties({
              struct: serializedKet
            }, {
              upc: unipositiveIonsValue / molarMeasurementUnitToNumber[unipositiveIonsMeasurementUnit],
              nac: oligonucleotidesValue / molarMeasurementUnitToNumber[oligonucleotidesMeasurementUnit]
            });
          case 17:
            calculateMacromoleculePropertiesResponse = _context.sent;
            try {
              macromoleculeProperties = calculateMacromoleculePropertiesResponse.properties && JSON.parse(calculateMacromoleculePropertiesResponse.properties);
              notifyRequestCompleted();
              dispatch2(setMacromoleculesProperties2(macromoleculeProperties));
            } catch (e) {
              KetcherLogger.error("Error during parsing macromolecule properties: ", e);
              dispatch2(setMacromoleculesProperties2(void 0));
            }
          case 19:
          case "end":
            return _context.stop();
        }
      }, _callee);
    }));
    return function(_x) {
      return _ref3.apply(this, arguments);
    };
  })();
};
var _excluded = ["className"];
function _createForOfIteratorHelper(r, e) {
  var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"];
  if (!t) {
    if (Array.isArray(r) || (t = _unsupportedIterableToArray(r)) || e) {
      t && (r = t);
      var _n = 0, F = function F2() {
      };
      return { s: F, n: function n() {
        return _n >= r.length ? { done: true } : { done: false, value: r[_n++] };
      }, e: function e3(r2) {
        throw r2;
      }, f: F };
    }
    throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.");
  }
  var o, a = true, u = false;
  return { s: function s() {
    t = t.call(r);
  }, n: function n() {
    var r2 = t.next();
    return a = r2.done, r2;
  }, e: function e3(r2) {
    u = true, o = r2;
  }, f: function f() {
    try {
      a || null == t["return"] || t["return"]();
    } finally {
      if (u) throw o;
    }
  } };
}
function _unsupportedIterableToArray(r, a) {
  if (r) {
    if ("string" == typeof r) return _arrayLikeToArray(r, a);
    var t = {}.toString.call(r).slice(8, -1);
    return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a) : void 0;
  }
}
function _arrayLikeToArray(r, a) {
  (null == a || a > r.length) && (a = r.length);
  for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e];
  return n;
}
function ownKeys$3(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$3(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$3(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$3(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var OTHER_MONOMER_COUNT_NAME = "Other";
var hasSpecificProperty = function hasSpecificProperty2(macromoleculesProperties, property) {
  var _macromoleculesProper;
  var specificProperty = macromoleculesProperties === null || macromoleculesProperties === void 0 || (_macromoleculesProper = macromoleculesProperties.monomerCount) === null || _macromoleculesProper === void 0 ? void 0 : _macromoleculesProper[property];
  return specificProperty && Object.keys(specificProperty).length > 0;
};
var StyledWrapper = createStyled("div", {
  target: "eifx56c30"
} )(function(_ref3) {
  var hasError = _ref3.hasError;
  return {
    width: "100%",
    height: hasError ? "124px" : "177px",
    position: "relative",
    backgroundColor: "white",
    padding: "2px 0",
    borderRadius: "8px 8px",
    overflow: "hidden",
    boxShadow: "0px 2px 5px rgba(103, 104, 132, 0.15)"
  };
}, "" );
var WindowControlsArea = createStyled("div", {
  target: "eifx56c29"
} )(function() {
  return {
    display: "flex"
  };
}, "" );
var WindowDragControl = createStyled("div", {
  target: "eifx56c28"
} )(function() {
  return {
    flex: 1,
    display: "flex",
    justifyContent: "center"
  };
}, "" );
var StyledCloseIcon = createStyled(Icon, {
  target: "eifx56c27"
} )(function() {
  return {
    display: "flex",
    alignItems: "center",
    width: "12px",
    height: "12px",
    padding: "2px 6px",
    cursor: "pointer"
  };
}, "" );
var Header = createStyled("div", {
  target: "eifx56c26"
} )(function() {
  return {
    display: "flex",
    height: "25px",
    alignItems: "center",
    padding: "0 8px"
  };
}, "" );
var GrossFormula = createStyled("div", {
  target: "eifx56c25"
} )(function() {
  return {
    display: "flex",
    alignItems: "center",
    fontSize: "14px",
    fontWeight: "700",
    padding: "0 8px",
    color: "#585858"
  };
}, "" );
var MolecularMass = createStyled("div", {
  target: "eifx56c24"
} )(function() {
  return {
    display: "flex",
    alignItems: "center",
    height: "24px",
    borderLeft: "1px solid #CAD3DD",
    color: "#585858"
  };
}, "" );
var MolecularMassAmount = createStyled("div", {
  target: "eifx56c23"
} )(function() {
  return {
    fontSize: "14px",
    fontWeight: "700",
    padding: "0 8px"
  };
}, "" );
var TabsWrapper = createStyled("div", {
  target: "eifx56c22"
} )(function() {
  return {
    width: "100%",
    height: "100%",
    top: "-25px",
    position: "relative"
  };
}, "" );
var TabContentWrapper = createStyled("div", {
  target: "eifx56c21"
} )(function() {
  return {
    width: "100%",
    padding: "0 4px 4px"
  };
}, "" );
var TabContentErrorWrapper = createStyled("div", {
  target: "eifx56c20"
} )(function() {
  return {
    display: "flex",
    width: "100%",
    height: "74px",
    flexDirection: "column",
    justifyContent: "center",
    alignItems: "center"
  };
}, "" );
var TabContentErrorTitle = createStyled("div", {
  target: "eifx56c19"
} )(function() {
  return {
    fontSize: "14px"
  };
}, "" );
var TabContentErrorDescription = createStyled("div", {
  target: "eifx56c18"
} )(function() {
  return {
    fontSize: "12px"
  };
}, "" );
var BasicPropertiesWrapper = createStyled("div", {
  target: "eifx56c17"
} )(function() {
  return {
    display: "flex",
    padding: "4px 0px",
    height: "32px",
    gap: "12px"
  };
}, "" );
var PeptidePropertiesBottomPart = createStyled("div", {
  target: "eifx56c16"
} )(function() {
  return {
    display: "grid",
    gridTemplateColumns: "2fr 1fr",
    gap: "0 2px"
  };
}, "" );
var HydrophobicityChartWrapper = createStyled("div", {
  target: "eifx56c15"
} )(function() {
  return {
    height: "90px",
    backgroundColor: "white",
    borderRadius: "8px",
    padding: "5px"
  };
}, "" );
var RnaBasicPropertiesWrapper = createStyled("div", {
  target: "eifx56c14"
} )(function() {
  return {
    display: "flex",
    justifyContent: "space-between"
  };
}, "" );
var PeptideBasicPropertiesWrapper = createStyled("div", {
  target: "eifx56c13"
} )(function() {
  return {
    display: "grid",
    gridTemplateColumns: "2fr 1fr"
  };
}, "" );
var StyledBasicProperty = createStyled("div", {
  target: "eifx56c12"
} )(function(_ref22) {
  var disabled = _ref22.disabled;
  return {
    display: "flex",
    alignItems: "center",
    padding: "0 0 0 6px",
    pointerEvents: disabled ? "none" : "auto",
    opacity: disabled ? 0.5 : 1
  };
}, "" );
var StyledTooltip = createStyled(function(_ref3) {
  var className = _ref3.className, props = _objectWithoutProperties(_ref3, _excluded);
  return jsx(Tooltip, _objectSpread$3(_objectSpread$3({}, props), {}, {
    classes: {
      popper: className
    }
  }));
}, {
  target: "eifx56c11"
} )(function() {
  return _defineProperty$1({}, "& .".concat(tooltipClasses.tooltip), {
    maxWidth: "220px",
    padding: "12px",
    backgroundColor: "white",
    color: "rgba(0, 0, 0, 0.87)",
    boxShadow: "0 1px 5px 0 #CCCCCC",
    fontSize: 11
  });
}, "" );
var HydrophobicityHintHeader = createStyled("div", {
  target: "eifx56c10"
} )(function() {
  return {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    fontSize: "12px",
    fontWeight: "700",
    color: "#585858",
    borderBottom: "1px solid #585858",
    paddingBottom: "8px",
    marginBottom: "8px"
  };
}, "" );
var BasicPropertyName = createStyled("div", {
  target: "eifx56c9"
} )(function() {
  return {
    fontSize: "10px",
    paddingRight: "5px",
    whiteSpace: "nowrap"
  };
}, "" );
var BasicPropertyValue = createStyled("div", {
  target: "eifx56c8"
} )(function() {
  return {
    fontSize: "14px",
    fontWeight: "700"
  };
}, "" );
var PropertyHintIcon = createStyled(Icon, {
  target: "eifx56c7"
} )(function() {
  return {
    width: "20px",
    height: "20px"
  };
}, "" );
var PropertyHintIconWrapper = createStyled("div", {
  target: "eifx56c6"
} )(function() {
  return {
    display: "flex",
    alignItems: "center"
  };
}, "" );
var BasicPropertyDropdown = createStyled(DropDown, {
  target: "eifx56c5"
} )(function() {
  return {
    position: "relative",
    padding: "0 0 0 5px",
    zIndex: 1
  };
}, "" );
var inputClassName = "text-input-field-input";
var BasicPropertyInput = createStyled(TextInputField, {
  target: "eifx56c4"
} )(function() {
  return _defineProperty$1({
    margin: 0
  }, ".".concat(inputClassName), {
    width: "60px",
    "::-webkit-inner-spin-button": {
      WebkitAppearance: "none",
      margin: 0
    },
    "::-webkit-outer-spin-button": {
      WebkitAppearance: "none",
      margin: 0
    },
    MozAppearance: "textfield"
  });
}, "" );
var StyledMonomersCountPanel = createStyled("div", {
  target: "eifx56c3"
} )(function() {
  return {
    display: "grid",
    gridTemplateColumns: "repeat(8, 1fr)",
    gap: "4px 6px",
    width: "100%",
    backgroundColor: "white",
    borderRadius: "8px",
    padding: "6px",
    height: "90px",
    alignContent: "flex-start"
  };
}, "" );
var StyledMonomersCountPanelItem = createStyled("div", {
  target: "eifx56c2"
} )("display:flex;position:relative;justify-content:space-between;background-color:#eff2f5;padding:4px 6px;font-weight:500;font-size:12px;border-radius:2px;min-width:50px;flex:1;opacity:", function(_ref6) {
  var disabled = _ref6.disabled;
  return disabled ? 0.4 : 1;
}, ";&:after{content:'';position:absolute;bottom:0;left:0;width:15px;height:2px;background:", function(_ref7) {
  var _colorsMap$monomerSho;
  var theme = _ref7.theme, monomerShortName = _ref7.monomerShortName, isPeptide = _ref7.isPeptide;
  var colorsMap = isPeptide ? theme.ketcher.peptide.color : theme.ketcher.monomer.color;
  return ((_colorsMap$monomerSho = colorsMap[monomerShortName]) === null || _colorsMap$monomerSho === void 0 ? void 0 : _colorsMap$monomerSho.regular) || theme.ketcher.monomer.color["default"].regular;
}, ";border-radius:0 0 0 2px;}" + ("" ));
var StyledMonomersCountPanelItemName = createStyled("div", {
  target: "eifx56c1"
} )(function() {
  return {
    fontWeight: "700"
  };
}, "" );
var MonomersCountPanel = function MonomersCountPanel2(props) {
  var naturalAnaloguesArray = props.isPeptide ? peptideNaturalAnalogues : rnaDnaNaturalAnalogues;
  var countsEntries = naturalAnaloguesArray.map(function(peptideNaturalAnalogues2) {
    return [peptideNaturalAnalogues2, props.monomerCount[peptideNaturalAnalogues2] || 0];
  });
  countsEntries.push([OTHER_MONOMER_COUNT_NAME, props.monomerCount[OTHER_MONOMER_COUNT_NAME] || 0]);
  countsEntries.sort(function(a, b) {
    return a[0] === OTHER_MONOMER_COUNT_NAME ? 1 : a[0].localeCompare(b[0]);
  });
  return jsx(StyledMonomersCountPanel, {
    children: _map(countsEntries, function(_ref8) {
      var _ref9 = _slicedToArray(_ref8, 2), monomerShortName = _ref9[0], count = _ref9[1];
      return jsxs(StyledMonomersCountPanelItem, {
        monomerShortName,
        "data-testid": monomerShortName + "-option",
        isPeptide: props.isPeptide,
        disabled: count === 0,
        children: [jsx(StyledMonomersCountPanelItemName, {
          children: monomerShortName
        }), jsx("div", {
          children: count
        })]
      }, monomerShortName);
    })
  });
};
var BasicProperty = function BasicProperty2(props) {
  var _props$value;
  return jsx(StyledBasicProperty, {
    "data-testid": props.testId,
    disabled: props.disabled,
    children: jsxs(Fragment, {
      children: [jsxs(BasicPropertyName, {
        children: [props.name, props.value !== void 0 && ":"]
      }), props.onChangeValue ? jsx(BasicPropertyInput, {
        value: (_props$value = props.value) !== null && _props$value !== void 0 ? _props$value : "",
        id: "macromolecule-property-".concat(props.name),
        "data-testid": "".concat(props.testId, "-input"),
        type: "number",
        min: 0,
        inputClassName,
        onChange: function onChange(value) {
          var _props$onChangeValue;
          return props === null || props === void 0 || (_props$onChangeValue = props.onChangeValue) === null || _props$onChangeValue === void 0 ? void 0 : _props$onChangeValue.call(props, Number(value));
        }
      }) : jsx(BasicPropertyValue, {
        "data-testid": props.testId + "-value",
        children: props.value
      }), props.hint && jsx(StyledTooltip, {
        title: props.hint,
        children: jsx(PropertyHintIconWrapper, {
          children: jsx(PropertyHintIcon, {
            name: "about",
            dataTestId: props.name + "-info"
          })
        })
      }), props.options && props.selectedOption && props.onChangeOption && jsx(BasicPropertyDropdown, {
        options: props.options.map(function(option) {
          return {
            id: option,
            label: option
          };
        }),
        testId: props.testId + "-selector",
        currentSelection: props.selectedOption,
        selectionHandler: props.onChangeOption
      })]
    })
  });
};
var GrossFormulaPart = function GrossFormulaPart2(_ref0) {
  var part = _ref0.part;
  var match = part.match(/^([A-Za-z]+)(\d+)$/);
  if (!match) return part;
  var _match = _slicedToArray(match, 3);
  _match[0];
  var element = _match[1], count = _match[2];
  return jsxs("span", {
    children: [element, jsx("sub", {
      children: count
    })]
  });
};
var StyledHydrophobicityChartSvg = createStyled("svg", {
  target: "eifx56c0"
} )(function() {
  return {
    width: "100%",
    height: "100%"
  };
}, "" );
function lttb(xs, ys, threshold) {
  var dataLength = xs.length;
  if (threshold >= dataLength || threshold === 0) {
    return {
      xs,
      ys
    };
  }
  var sampledXs = [xs[0]];
  var sampledYs = [ys[0]];
  var every = (dataLength - 2) / (threshold - 2);
  var a = 0;
  for (var i = 0; i < threshold - 2; i++) {
    var rangeStart = Math.floor((i + 1) * every) + 1;
    var rangeEnd = Math.floor((i + 2) * every) + 1;
    var avgRangeStart = rangeStart;
    var avgRangeEnd = rangeEnd;
    var avgX = 0;
    var avgY = 0;
    var rangeLength = avgRangeEnd - avgRangeStart;
    for (var j = avgRangeStart; j < avgRangeEnd; j++) {
      avgX += xs[j];
      avgY += ys[j];
    }
    avgX /= rangeLength;
    avgY /= rangeLength;
    var rangeOffs = Math.floor(i * every) + 1;
    var rangeTo = Math.floor((i + 1) * every) + 1;
    var maxArea = -1;
    var nextA = rangeOffs;
    for (var _j = rangeOffs; _j < rangeTo; _j++) {
      var area = Math.abs((xs[a] - avgX) * (ys[_j] - ys[a]) - (xs[a] - xs[_j]) * (avgY - ys[a]));
      if (area > maxArea) {
        maxArea = area;
        nextA = _j;
      }
    }
    sampledXs.push(xs[nextA]);
    sampledYs.push(ys[nextA]);
    a = nextA;
  }
  sampledXs.push(xs[dataLength - 1]);
  sampledYs.push(ys[dataLength - 1]);
  return {
    xs: sampledXs,
    ys: sampledYs
  };
}
var getNumberOfTicks = function getNumberOfTicks2(_width) {
  if (_width > 360) {
    return 5;
  } else if (_width > 300) {
    return 4;
  } else if (_width > 240) {
    return 3;
  }
  return 2;
};
var roundToMinNiceNumber = function roundToMinNiceNumber2(number2) {
  if (number2 < 1) {
    return 0;
  } else if (number2 < 2) {
    return 1;
  } else if (number2 < 3) {
    return 2;
  } else if (number2 < 5) {
    return 3;
  } else if (number2 < 10) {
    return 5;
  } else if (number2 < 100) {
    return Math.floor(number2 / 10) * 10;
  } else if (number2 < 1e3) {
    return Math.floor(number2 / 50) * 50;
  }
  return Math.floor(number2 / 100) * 100;
};
var HydrophobicityChart = function HydrophobicityChart2(props) {
  var initialData = props.data;
  var data = lttb(initialData.map(function(_item, index) {
    return index + 1;
  }), initialData, 100);
  var _useState = reactExports.useState(0), _useState2 = _slicedToArray(_useState, 2), containerWidth = _useState2[0], setContainerWidth = _useState2[1];
  var svgRef = reactExports.useRef(null);
  reactExports.useEffect(function() {
    if (!data.xs.length || !svgRef.current) return;
    var width = svgRef.current.width.baseVal.value;
    var height = svgRef.current.height.baseVal.value;
    var margin = {
      top: 10,
      right: 10,
      bottom: 20,
      left: 30
    };
    select(svgRef.current).selectAll("*").remove();
    var xScale = linear().domain([0, data.xs.length - 1]).range([margin.left, width - margin.right]);
    var yScale = linear().domain([0, 1]).range([height - margin.bottom, margin.top]);
    var line$1 = line().x(function(_d, i2) {
      return xScale(i2);
    }).y(function(d) {
      return yScale(d);
    }).curve(curveLinear);
    var svgContainer = select(svgRef.current);
    var maximumNumberOfTicks = getNumberOfTicks(width);
    var distanceBetweenTicksForMaximumNumberOfTicks = roundToMinNiceNumber(initialData.length / maximumNumberOfTicks);
    var finalDistanceBetweenTicks = distanceBetweenTicksForMaximumNumberOfTicks;
    var tickValues;
    if (distanceBetweenTicksForMaximumNumberOfTicks >= 1) {
      var numberOfTicksWithMaximumCoverage = -Infinity;
      var distanceBetweenTicksWithMaximumCoverage = -Infinity;
      var maximumCoverage = -Infinity;
      for (var i = 2; i <= maximumNumberOfTicks; i++) {
        var numberOfTicks = i;
        var distanceBetweenTicks = roundToMinNiceNumber(initialData.length / numberOfTicks);
        var coverage = Number((distanceBetweenTicks * (numberOfTicks / initialData.length)).toFixed(2));
        if (coverage > maximumCoverage || coverage === maximumCoverage && numberOfTicks > numberOfTicksWithMaximumCoverage) {
          numberOfTicksWithMaximumCoverage = numberOfTicks;
          maximumCoverage = coverage;
          distanceBetweenTicksWithMaximumCoverage = distanceBetweenTicks;
        }
      }
      tickValues = Array.from({
        length: numberOfTicksWithMaximumCoverage
      }, function(_2, i2) {
        return data.xs.findLastIndex(function(xDataItem) {
          return xDataItem <= (i2 + 1) * distanceBetweenTicksWithMaximumCoverage && xDataItem > i2 * distanceBetweenTicksWithMaximumCoverage;
        });
      });
      finalDistanceBetweenTicks = distanceBetweenTicksWithMaximumCoverage;
    } else {
      tickValues = _toConsumableArray(Array(Math.min(maximumNumberOfTicks, data.xs.length)).keys());
      finalDistanceBetweenTicks = 1;
    }
    var xAxis = axisBottom(xScale).tickValues(tickValues).tickFormat(function(_2, i2) {
      return ((i2 + 1) * finalDistanceBetweenTicks).toString();
    });
    svgContainer.append("g").attr("transform", "translate(0,".concat(height - margin.bottom, ")")).call(xAxis).call(function(g) {
      return g.select(".domain").remove();
    }).call(function(g) {
      return g.selectAll("line").attr("stroke", "#CAD3DD").attr("y1", -height);
    }).call(function(g) {
      return g.selectAll("text").attr("font-size", "8px");
    });
    var yAxis = axisLeft(yScale).tickValues([0, 0.5, 1]).tickFormat(format(".1f"));
    svgContainer.append("g").attr("transform", "translate(".concat(margin.left, ",0)")).call(yAxis).call(function(g) {
      return g.select(".domain").remove();
    }).call(function(g) {
      g.selectAll("line").each(function(value, index, lines) {
        if (value === 0.5) {
          select(lines[index]).attr("x1", width).attr("stroke", "#CAD3DD").attr("stroke-dasharray", 2);
        } else {
          select(lines[index]).remove();
        }
      });
    }).call(function(g) {
      return g.selectAll("text").attr("font-size", "8px");
    });
    svgContainer.append("path").datum(data.ys).attr("fill", "none").attr("stroke", "#167782").attr("stroke-width", 1).attr("d", line$1);
  }, [initialData, containerWidth]);
  var resizeObserver = new ResizeObserver(lodashExports.debounce(function(entries) {
    var _iterator = _createForOfIteratorHelper(entries), _step;
    try {
      for (_iterator.s(); !(_step = _iterator.n()).done; ) {
        var entry = _step.value;
        if (entry.contentRect.width !== containerWidth) {
          setContainerWidth(entry.contentRect.width);
        }
      }
    } catch (err) {
      _iterator.e(err);
    } finally {
      _iterator.f();
    }
  }, 100));
  reactExports.useEffect(function() {
    if (svgRef.current) {
      resizeObserver.observe(svgRef.current);
    }
    return function() {
      resizeObserver.disconnect();
    };
  }, [svgRef, containerWidth]);
  return jsx(StyledHydrophobicityChartSvg, {
    "data-testid": "Hydrophobicity-Chart",
    ref: svgRef
  });
};
var PeptideProperties = function PeptideProperties2(props) {
  return props.isError ? jsxs(TabContentErrorWrapper, {
    children: [jsx(TabContentErrorTitle, {
      children: "No Data Available"
    }), jsx(TabContentErrorDescription, {
      children: "Select monomer, chain or part of a chain"
    })]
  }) : jsxs(TabContentWrapper, {
    children: [jsxs(PeptideBasicPropertiesWrapper, {
      children: [jsxs(BasicPropertiesWrapper, {
        children: [jsx(BasicProperty, {
          name: "Isoelectric Point",
          testId: "Isoelectric Point",
          value: lodashExports.isNumber(props.macromoleculesProperties.pKa) ? _round(props.macromoleculesProperties.pKa, 2) : "–",
          hint: "The isoelectric point is calculated as the median of all pKa values for the structure."
        }), jsx(BasicProperty, {
          name: "Extinction Coef.(1/Mcm)",
          testId: "Extinction Coefficient",
          value: lodashExports.isNumber(props.macromoleculesProperties.extinctionCoefficient) ? _round(props.macromoleculesProperties.extinctionCoefficient) : "–",
          hint: jsxs("div", {
            children: ["The extinction coefficient for wavelength of 280nm is calculated using the method from", " ", jsx("i", {
              children: "Gill, S.C. and von Hippel, P.H. (1989)."
            }), " Natural analogue is used in place of a modified amino acid."]
          })
        })]
      }), jsx(BasicProperty, {
        name: "Hydrophobicity",
        testId: "Hydrophobicity",
        hint: jsxs("div", {
          children: [jsxs(HydrophobicityHintHeader, {
            children: [jsx("div", {
              children: "y = Hydrophobicity score"
            }), jsx("div", {
              children: "x = Position of the amino acid residue"
            })]
          }), "The hydrophobicity is calculated using the method from", " ", jsx("i", {
            children: "Black S.D. and Mould D.R. (1991)."
          }), " Natural analogue is used in place of a modified amino acid."]
        })
      })]
    }), jsxs(PeptidePropertiesBottomPart, {
      children: [props.macromoleculesProperties.monomerCount.peptides && jsx(MonomersCountPanel, {
        monomerCount: props.macromoleculesProperties.monomerCount.peptides,
        isPeptide: true
      }), jsx(HydrophobicityChartWrapper, {
        children: props.macromoleculesProperties.hydrophobicity && jsx(HydrophobicityChart, {
          data: props.macromoleculesProperties.hydrophobicity
        })
      })]
    })]
  });
};
var containOnlyPartOfNumber = function containOnlyPartOfNumber2(value) {
  return !/[^0.,]/.test(String(value));
};
var RnaProperties = function RnaProperties2(props) {
  var dispatch2 = useAppDispatch();
  var unipositiveIonsMeasurementUnit = useAppSelector(selectUnipositiveIonsMeasurementUnit);
  var oligonucleotidesMeasurementUnit = useAppSelector(selectOligonucleotidesMeasurementUnit);
  var unipositiveIonsValue = useAppSelector(selectUnipositiveIonsValue);
  var oligonucleotidesValue = useAppSelector(selectOligonucleotidesValue);
  var onChangeUnipositiveIonsMeasurementUnit = function onChangeUnipositiveIonsMeasurementUnit2(option) {
    dispatch2(setUnipositiveIonsMeasurementUnit2(option));
  };
  var onChangeOligonucleotidesMeasurementUnit = function onChangeOligonucleotidesMeasurementUnit2(option) {
    dispatch2(setOligonucleotidesMeasurementUnit2(option));
  };
  var onChangeUnipositiveIonsValue = function onChangeUnipositiveIonsValue2(value) {
    dispatch2(setUnipositiveIonsValue2(value.toString()));
  };
  var onChangeOligonucleotidesValue = function onChangeOligonucleotidesValue2(value) {
    dispatch2(setOligonucleotidesValue2(value.toString()));
  };
  return props.isError ? jsxs(TabContentErrorWrapper, {
    children: [jsx(TabContentErrorTitle, {
      children: "No Data Available"
    }), jsx(TabContentErrorDescription, {
      children: "Select a nucleotide/nucleoside, chain or part of a chain containing nucleotides/nucleosides"
    })]
  }) : jsxs(TabContentWrapper, {
    children: [jsxs(RnaBasicPropertiesWrapper, {
      children: [lodashExports.isNumber(props.macromoleculesProperties.Tm) ? jsx(BasicProperty, {
        name: "Melting Temp. (°C)",
        value: _round(props.macromoleculesProperties.Tm, 1),
        testId: "Melting-Temperature",
        hint: jsxs("div", {
          children: ["The melting temperature is calculated using the method from", " ", jsx("i", {
            children: "Khandelwal G. and Bhyravabhotla J. (2010)."
          }), " Natural analogue is used in place of a modified base."]
        })
      }) : jsx("div", {}), jsxs(BasicPropertiesWrapper, {
        children: [jsx(BasicProperty, {
          name: "[Unipositive Ions]",
          value: unipositiveIonsValue,
          options: ["nM", "μM", "mM"],
          testId: "Unipositive Ions",
          selectedOption: unipositiveIonsMeasurementUnit,
          disabled: !lodashExports.isNumber(props.macromoleculesProperties.Tm) && !containOnlyPartOfNumber(unipositiveIonsValue),
          onChangeOption: onChangeUnipositiveIonsMeasurementUnit,
          onChangeValue: onChangeUnipositiveIonsValue
        }), jsx(BasicProperty, {
          name: "[Oligonucleotides]",
          value: oligonucleotidesValue,
          options: ["nM", "μM", "mM"],
          testId: "Oligonucleotides",
          selectedOption: oligonucleotidesMeasurementUnit,
          disabled: !lodashExports.isNumber(props.macromoleculesProperties.Tm) && !containOnlyPartOfNumber(oligonucleotidesValue),
          onChangeOption: onChangeOligonucleotidesMeasurementUnit,
          onChangeValue: onChangeOligonucleotidesValue
        })]
      })]
    }), props.macromoleculesProperties.monomerCount.nucleotides && jsx(MonomersCountPanel, {
      monomerCount: props.macromoleculesProperties.monomerCount.nucleotides
    })]
  });
};
var PROPERTIES_TABS;
(function(PROPERTIES_TABS2) {
  PROPERTIES_TABS2[PROPERTIES_TABS2["PEPTIDES"] = 0] = "PEPTIDES";
  PROPERTIES_TABS2[PROPERTIES_TABS2["RNA"] = 1] = "RNA";
  PROPERTIES_TABS2[PROPERTIES_TABS2["NO_TAB"] = -1] = "NO_TAB";
})(PROPERTIES_TABS || (PROPERTIES_TABS = {}));
var MassMeasurementUnit;
(function(MassMeasurementUnit2) {
  MassMeasurementUnit2["Da"] = "Da";
  MassMeasurementUnit2["kDa"] = "kDa";
  MassMeasurementUnit2["MDa"] = "MDa";
})(MassMeasurementUnit || (MassMeasurementUnit = {}));
var massMeasurementUnitToNumber = _defineProperty$1(_defineProperty$1(_defineProperty$1({}, MassMeasurementUnit.Da, 1), MassMeasurementUnit.kDa, 1e3), MassMeasurementUnit.MDa, 1e6);
var calculateMassMeasurementUnit = function calculateMassMeasurementUnit2(mass) {
  if (!lodashExports.isNumber(mass)) {
    return MassMeasurementUnit.Da;
  }
  if (mass < 1e3) {
    return MassMeasurementUnit.Da;
  }
  if (mass < 1e6) {
    return MassMeasurementUnit.kDa;
  }
  return MassMeasurementUnit.MDa;
};
var selectEntitiesHandler;
var MacromoleculePropertiesWindow = function MacromoleculePropertiesWindow2() {
  var dispatch2 = useAppDispatch();
  var editor = useAppSelector(selectEditor);
  var macromoleculesProperties = useAppSelector(selectMacromoleculesProperties);
  var unipositiveIonsMeasurementUnit = useAppSelector(selectUnipositiveIonsMeasurementUnit);
  var oligonucleotidesMeasurementUnit = useAppSelector(selectOligonucleotidesMeasurementUnit);
  var unipositiveIonsValue = useAppSelector(selectUnipositiveIonsValue);
  var oligonucleotidesValue = useAppSelector(selectOligonucleotidesValue);
  var firstMacromoleculesProperties = macromoleculesProperties === null || macromoleculesProperties === void 0 ? void 0 : macromoleculesProperties[0];
  var _useState3 = reactExports.useState(PROPERTIES_TABS.PEPTIDES), _useState4 = _slicedToArray(_useState3, 2), selectedTabIndex = _useState4[0], setSelectedTabIndex3 = _useState4[1];
  var _useState5 = reactExports.useState(calculateMassMeasurementUnit(firstMacromoleculesProperties === null || firstMacromoleculesProperties === void 0 ? void 0 : firstMacromoleculesProperties.mass)), _useState6 = _slicedToArray(_useState5, 2), massMeasurementUnit = _useState6[0], setMassMeasurementUnit = _useState6[1];
  var isMacromoleculesPropertiesWindowOpened = useAppSelector(selectIsMacromoleculesPropertiesWindowOpened);
  var recalculateMacromoleculeProperties = useRecalculateMacromoleculeProperties();
  var skipDataFetch = !isMacromoleculesPropertiesWindowOpened;
  var recalculateMacromoleculePropertiesRef = reactExports.useRef(recalculateMacromoleculeProperties);
  var debouncedRecalculateMacromoleculeProperties = reactExports.useCallback(lodashExports.debounce(function(shouldSkip) {
    recalculateMacromoleculePropertiesRef.current(shouldSkip);
  }, 500), []);
  reactExports.useEffect(function() {
    recalculateMacromoleculePropertiesRef.current = function(shouldSkip) {
      recalculateMacromoleculeProperties(shouldSkip);
    };
  }, [recalculateMacromoleculeProperties]);
  reactExports.useEffect(function() {
    if (selectEntitiesHandler && editor !== null && editor !== void 0 && editor.events.selectEntities.hasHandler(selectEntitiesHandler)) {
      editor === null || editor === void 0 || editor.events.selectEntities.remove(selectEntitiesHandler);
    }
    selectEntitiesHandler = function selectEntitiesHandler2() {
      debouncedRecalculateMacromoleculeProperties(skipDataFetch);
    };
    editor === null || editor === void 0 || editor.events.selectEntities.add(selectEntitiesHandler);
    return function() {
      editor === null || editor === void 0 || editor.events.selectEntities.remove(selectEntitiesHandler);
    };
  }, [debouncedRecalculateMacromoleculeProperties, editor, skipDataFetch]);
  reactExports.useEffect(function() {
    debouncedRecalculateMacromoleculeProperties(skipDataFetch);
  }, [unipositiveIonsMeasurementUnit, oligonucleotidesMeasurementUnit, unipositiveIonsValue, oligonucleotidesValue, skipDataFetch, debouncedRecalculateMacromoleculeProperties]);
  reactExports.useEffect(function() {
    setSelectedTabIndex3(hasSpecificProperty(firstMacromoleculesProperties, "nucleotides") ? PROPERTIES_TABS.RNA : PROPERTIES_TABS.PEPTIDES);
    setMassMeasurementUnit(calculateMassMeasurementUnit(firstMacromoleculesProperties === null || firstMacromoleculesProperties === void 0 ? void 0 : firstMacromoleculesProperties.mass));
  }, [firstMacromoleculesProperties]);
  var onTabChange = function onTabChange2(_event, newValue) {
    setSelectedTabIndex3(newValue);
  };
  var closeWindow = function closeWindow2() {
    dispatch2(setMacromoleculesPropertiesWindowVisibility2(false));
  };
  var onMassMeasurementUnitChange = function onMassMeasurementUnitChange2(option) {
    setMassMeasurementUnit(option);
  };
  var hasCommonError = !firstMacromoleculesProperties || macromoleculesProperties.length > 1;
  var hasPeptidesTabError = hasCommonError || !hasSpecificProperty(firstMacromoleculesProperties, "peptides");
  var hasNucleotidesTabError = hasCommonError || !hasSpecificProperty(firstMacromoleculesProperties, "nucleotides");
  var grossFormula = reactExports.useMemo(function() {
    if (!(firstMacromoleculesProperties !== null && firstMacromoleculesProperties !== void 0 && firstMacromoleculesProperties.grossFormula)) {
      return null;
    }
    return jsx(GrossFormula, {
      "data-testid": "Gross-formula",
      children: firstMacromoleculesProperties === null || firstMacromoleculesProperties === void 0 ? void 0 : firstMacromoleculesProperties.grossFormula.split(" ").map(function(atomNameWithAmount, index, array2) {
        return jsxs("span", {
          children: [jsx(GrossFormulaPart, {
            part: atomNameWithAmount
          }), index < array2.length - 1 ? " " : ""]
        }, "".concat(atomNameWithAmount, "-").concat(index));
      })
    });
  }, [firstMacromoleculesProperties === null || firstMacromoleculesProperties === void 0 ? void 0 : firstMacromoleculesProperties.grossFormula]);
  var molecularMassValue = reactExports.useMemo(function() {
    if (!(firstMacromoleculesProperties !== null && firstMacromoleculesProperties !== void 0 && firstMacromoleculesProperties.mass)) {
      return null;
    }
    return jsxs(Fragment, {
      children: [jsx(MolecularMassAmount, {
        "data-testid": "Molecular-Mass-Value",
        children: _round((firstMacromoleculesProperties === null || firstMacromoleculesProperties === void 0 ? void 0 : firstMacromoleculesProperties.mass) / massMeasurementUnitToNumber[massMeasurementUnit], 3)
      }), " "]
    });
  }, [firstMacromoleculesProperties === null || firstMacromoleculesProperties === void 0 ? void 0 : firstMacromoleculesProperties.mass, massMeasurementUnit]);
  return isMacromoleculesPropertiesWindowOpened ? jsxs(StyledWrapper, {
    hasError: selectedTabIndex === PROPERTIES_TABS.PEPTIDES && hasPeptidesTabError || selectedTabIndex === PROPERTIES_TABS.RNA && hasNucleotidesTabError,
    "data-testid": "macromolecule-properties-window",
    children: [jsxs(WindowControlsArea, {
      children: [jsx(WindowDragControl, {
        children: jsxs("svg", {
          width: "16",
          height: "16",
          viewBox: "0 0 16 16",
          fill: "none",
          xmlns: "http://www.w3.org/2000/svg",
          children: [jsx("path", {
            d: "M2 6H14",
            stroke: "#333333"
          }), jsx("path", {
            d: "M2 10H14",
            stroke: "#333333"
          })]
        })
      }), jsx(StyledCloseIcon, {
        name: "close",
        onClick: closeWindow,
        dataTestId: "macromolecule-properties-close"
      })]
    }), jsxs(Header, {
      children: [grossFormula, molecularMassValue && jsxs(MolecularMass, {
        children: [molecularMassValue, jsx(BasicPropertyDropdown, {
          testId: "Molecular Mass Unit",
          options: [MassMeasurementUnit.Da, MassMeasurementUnit.kDa, MassMeasurementUnit.MDa].map(function(unit2) {
            return {
              id: unit2,
              label: unit2
            };
          }),
          currentSelection: massMeasurementUnit,
          selectionHandler: onMassMeasurementUnitChange
        })]
      })]
    }), jsx(TabsWrapper, {
      children: jsx(Tabs$1, {
        selectedTabIndex,
        onChange: onTabChange,
        isLayoutToRight: true,
        tabs: [{
          caption: "Peptides",
          testId: "peptides-properties-tab",
          component: PeptideProperties,
          props: {
            macromoleculesProperties: firstMacromoleculesProperties,
            isError: hasPeptidesTabError
          }
        }, {
          caption: "RNA/DNA",
          component: RnaProperties,
          testId: "rna-properties-tab",
          props: {
            macromoleculesProperties: firstMacromoleculesProperties,
            isError: hasNucleotidesTabError
          }
        }]
      })
    })]
  }) : null;
};
var hotkeysShortcuts = generateMenuShortcuts(hotkeysConfiguration);
var getIntegerFromString = function getIntegerFromString2(zoomInput) {
  var zoomNumber = parseInt(zoomInput !== null && zoomInput !== void 0 ? zoomInput : "");
  if (isNaN(zoomNumber)) {
    return 0;
  }
  return zoomNumber;
};
var getValidZoom = function getValidZoom2(zoom, currentZoom) {
  if (zoom === 0) {
    return currentZoom;
  }
  var minAllowed = ZoomTool.instance.MINZOOMSCALE * 100;
  var maxAllowed = ZoomTool.instance.MAXZOOMSCALE * 100;
  if (zoom < minAllowed) {
    return minAllowed;
  }
  if (zoom > maxAllowed) {
    return maxAllowed;
  }
  return zoom;
};
var updateInputString = function updateInputString2(zoom, inputElement) {
  if (!inputElement) return;
  inputElement.value = "".concat(Math.round(zoom), "%");
};
var StyledButton$1 = createStyled(Button, {
  target: "e1pc97tg0"
} )(function(_ref3) {
  var theme = _ref3.theme, isActive = _ref3.isActive;
  return {
    width: "28px",
    height: "28px",
    backgroundColor: isActive ? theme.ketcher.color.button.group.active : "white",
    margin: "2px",
    padding: "0",
    borderRadius: "4px",
    outline: "none",
    ":hover": {
      backgroundColor: isActive ? theme.ketcher.color.button.group.hover : "white"
    },
    ":hover svg": {
      fill: isActive ? "white" : theme.ketcher.color.button.group.active
    }
  };
}, "" );
var CalculateMacromoleculePropertiesButton = function CalculateMacromoleculePropertiesButton2() {
  var dispatch2 = useAppDispatch();
  var isMacromoleculesPropertiesWindowOpened = useAppSelector(selectIsMacromoleculesPropertiesWindowOpened);
  var recalculateMacromoleculeProperties = useRecalculateMacromoleculeProperties();
  var handleClick = (function() {
    var _ref22 = _asyncToGenerator(_regeneratorRuntime.mark(function _callee() {
      var skipDataFetch;
      return _regeneratorRuntime.wrap(function _callee$(_context) {
        while (1) switch (_context.prev = _context.next) {
          case 0:
            skipDataFetch = !isMacromoleculesPropertiesWindowOpened;
            _context.next = 3;
            return recalculateMacromoleculeProperties(skipDataFetch);
          case 3:
            dispatch2(toggleMacromoleculesPropertiesWindowVisibility2({}));
            blurActiveElement();
          case 5:
          case "end":
            return _context.stop();
        }
      }, _callee);
    }));
    return function handleClick2() {
      return _ref22.apply(this, arguments);
    };
  })();
  return jsx(StyledButton$1, {
    isActive: isMacromoleculesPropertiesWindowOpened,
    onClick: handleClick,
    title: "Calculate properties (".concat(hotkeysShortcuts.toggleMacromoleculesPropertiesVisibility, ")"),
    "data-testid": "calculate-macromolecule-properties-button",
    children: jsx("svg", {
      width: "15",
      height: "16",
      viewBox: "0 0 15 16",
      xmlns: "http://www.w3.org/2000/svg",
      fill: isMacromoleculesPropertiesWindowOpened ? "white" : "#333333",
      children: jsx("path", {
        fillRule: "evenodd",
        clipRule: "evenodd",
        d: "M9.87727 1.65517H9.03053V4.46737L9.42288 5.12973C9.76799 5.04496 10.1287 5 10.5 5C12.9853 5 15 7.01472 15 9.5C15 10.6812 14.5449 11.7562 13.8004 12.559C14.4936 14.1572 13.3016 16 11.456 16H2.54694C0.627617 16 -0.60048 14.0008 0.302223 12.3451C1.6087 9.94883 3.5345 6.39671 4.51457 4.49368V1.65517H3.66783V0H9.87727V1.65517ZM12.2962 13.6272C11.746 13.867 11.1385 14 10.5 14C8.01472 14 6 11.9853 6 9.5C6 7.98987 6.74386 6.65348 7.88515 5.83725L7.33705 4.91194V1.65517H6.20806V4.88502L6.11866 5.05976C5.15873 6.93619 3.14099 10.658 1.79676 13.1235C1.49524 13.6765 1.9056 14.3448 2.54694 14.3448H11.456C11.9075 14.3448 12.2417 14.0139 12.2962 13.6272ZM13.5375 9.5C13.5375 11.1776 12.1776 12.5375 10.5 12.5375C8.82244 12.5375 7.4625 11.1776 7.4625 9.5C7.4625 7.82243 8.82244 6.4625 10.5 6.4625C12.1776 6.4625 13.5375 7.82243 13.5375 9.5Z"
      })
    })
  });
};
function TopMenuComponent() {
  var _editor$drawingEntiti;
  var dispatch2 = useAppDispatch();
  var activeTool = useAppSelector(selectEditorActiveTool);
  var editor = useAppSelector(selectEditor);
  var layoutMode = useLayoutMode();
  var isSequenceEditInRNABuilderMode = useAppSelector(selectIsSequenceEditInRNABuilderMode);
  var _useState = reactExports.useState([]), _useState2 = _slicedToArray(_useState, 2), selectedEntities = _useState2[0], setSelectedEntities = _useState2[1];
  var _useState3 = reactExports.useState(false), _useState4 = _slicedToArray(_useState3, 2), needOpenByMenuItemClick = _useState4[0], setNeedOpenByMenuItemClick = _useState4[1];
  var _useState5 = reactExports.useState(), _useState6 = _slicedToArray(_useState5, 2), antisenseActiveOption = _useState6[0], setAntisenseActiveOption = _useState6[1];
  var activeMenuItems = [activeTool];
  var isDisabled = isSequenceEditInRNABuilderMode;
  var lastSelectedSelectionMenuItem = useAppSelector(selectLastSelectedSelectionMenuItem);
  var isFlexMode = layoutMode === "flex-layout-mode";
  var selectedMonomers = selectedEntities.filter(function(entity) {
    return entity && typeof entity.forEachBond === "function";
  });
  var cyclicStructureFormationDisabled = ((_editor$drawingEntiti = editor === null || editor === void 0 ? void 0 : editor.drawingEntitiesManager.selectedMicromoleculeEntities.length) !== null && _editor$drawingEntiti !== void 0 ? _editor$drawingEntiti : 0) > 0 || !isCycleExistsForSelectedMonomers(selectedMonomers);
  reactExports.useEffect(function() {
    var selectEntitiesHandler2 = function selectEntitiesHandler3(selectedEntities2) {
      setSelectedEntities(selectedEntities2);
      if (selectedEntities2.length && !isAntisenseCreationDisabled(selectedEntities2)) {
        setNeedOpenByMenuItemClick(false);
        if (hasOnlyDeoxyriboseSugars(selectedEntities2)) {
          setAntisenseActiveOption("antisenseDnaStrand");
        } else if (hasOnlyRiboseSugars(selectedEntities2)) {
          setAntisenseActiveOption("antisenseRnaStrand");
        } else {
          setAntisenseActiveOption("antisenseStrand");
          setNeedOpenByMenuItemClick(true);
        }
      }
    };
    editor === null || editor === void 0 || editor.events.selectEntities.add(selectEntitiesHandler2);
    return function() {
      editor === null || editor === void 0 || editor.events.selectEntities.remove(selectEntitiesHandler2);
    };
  }, [editor]);
  var menuItemChanged = function menuItemChanged2(name) {
    if (modalComponentList[name]) {
      dispatch2(openModal2(name));
    } else if (name === "undo" || name === "redo") {
      editor === null || editor === void 0 || editor.events.selectHistory.dispatch(name);
    } else if (name === "clear") {
      editor === null || editor === void 0 || editor.events.resetSequenceEditMode.dispatch();
      editor === null || editor === void 0 || editor.events.selectTool.dispatch([name]);
      dispatch2(selectTool2(lastSelectedSelectionMenuItem));
      editor === null || editor === void 0 || editor.events.selectTool.dispatch([lastSelectedSelectionMenuItem]);
      if (isSequenceEditInRNABuilderMode) resetRnaBuilderAfterSequenceUpdate(dispatch2, editor);
    } else if (name === "antisenseRnaStrand" || name === "antisenseDnaStrand") {
      editor === null || editor === void 0 || editor.events.createAntisenseChain.dispatch(name === "antisenseDnaStrand");
    } else if (name === "arrange-ring") {
      editor === null || editor === void 0 || editor.events.layoutCircular.dispatch();
    }
  };
  return jsxs(Menu, {
    onItemClick: menuItemChanged,
    activeMenuItems,
    isHorizontal: true,
    children: [jsxs(Menu.Group, {
      isHorizontal: true,
      divider: true,
      children: [jsx(Menu.Item, {
        itemId: "clear",
        title: "Clear Canvas (".concat(hotkeysShortcuts.clear, ")"),
        testId: "clear-canvas"
      }), jsx(Menu.Item, {
        itemId: "open",
        title: "Open...",
        disabled: isDisabled,
        testId: "open-file-button"
      }), jsx(Menu.Item, {
        itemId: "save",
        title: "Save as...",
        testId: "save-file-button"
      })]
    }), jsxs(Menu.Group, {
      isHorizontal: true,
      divider: true,
      children: [jsx(Menu.Item, {
        itemId: "undo",
        title: "Undo (".concat(hotkeysShortcuts.undo, ")"),
        disabled: isDisabled,
        testId: "undo"
      }), jsx(Menu.Item, {
        itemId: "redo",
        title: "Redo (".concat(hotkeysShortcuts.redo, ")"),
        disabled: isDisabled,
        testId: "redo"
      })]
    }), isFlexMode && jsx(Menu.Group, {
      isHorizontal: true,
      divider: true,
      children: jsx(Menu.Item, {
        itemId: "arrange-ring",
        title: "Arrange as a Ring (".concat(hotkeysShortcuts.arrangeRing, ")"),
        disabled: cyclicStructureFormationDisabled,
        testId: "arrange-ring"
      })
    }), jsxs(Menu.Group, {
      isHorizontal: true,
      children: [jsxs(Menu.Submenu, {
        disabled: !(selectedEntities !== null && selectedEntities !== void 0 && selectedEntities.length) || !isAntisenseOptionVisible(selectedEntities) || isAntisenseCreationDisabled(selectedEntities),
        needOpenByMenuItemClick,
        vertical: true,
        autoSize: true,
        layoutModeButton: true,
        generalTitle: "Create Antisense Strand",
        testId: "Create Antisense Strand",
        activeItem: antisenseActiveOption,
        children: [jsx(Menu.Item, {
          itemId: "antisenseRnaStrand",
          title: "Create RNA Antisense Strand (".concat(hotkeysShortcuts.createRnaAntisenseStrand, ")"),
          disabled: !(selectedEntities !== null && selectedEntities !== void 0 && selectedEntities.length) || !isAntisenseOptionVisible(selectedEntities) || isAntisenseCreationDisabled(selectedEntities),
          testId: "antisenseRnaStrand",
          type: "button"
        }), jsx(Menu.Item, {
          itemId: "antisenseDnaStrand",
          title: "Create DNA Antisense Strand (".concat(hotkeysShortcuts.createDnaAntisenseStrand, ")"),
          disabled: !(selectedEntities !== null && selectedEntities !== void 0 && selectedEntities.length) || !isAntisenseOptionVisible(selectedEntities) || isAntisenseCreationDisabled(selectedEntities),
          testId: "antisenseDnaStrand",
          type: "button"
        })]
      }), jsx(CalculateMacromoleculePropertiesButton, {})]
    })]
  });
}
function LeftMenuComponent() {
  var activeTool = useAppSelector(selectEditorActiveTool);
  var editor = useAppSelector(selectEditor);
  var isSequenceMode = useLayoutMode() === "sequence-layout-mode";
  var activeMenuItems = [activeTool];
  var menuItemChanged = function menuItemChanged2(name) {
    editor === null || editor === void 0 || editor.events.selectTool.dispatch([name, {
      toolName: name
    }]);
  };
  return jsxs(Menu, {
    testId: "left-toolbar",
    onItemClick: menuItemChanged,
    activeMenuItems,
    children: [jsxs(Menu.Group, {
      divider: true,
      children: [jsx(Menu.Item, {
        itemId: "hand",
        title: "Hand Tool (".concat(hotkeysShortcuts.hand, ")"),
        testId: "hand"
      }), jsx(Menu.Group, {
        children: jsxs(Menu.Submenu, {
          testId: "select-drop-down-button",
          subMenuId: SELECT_SUBMENU_ID,
          needOpenByMenuItemClick: true,
          children: [jsx(Menu.Item, {
            itemId: "select-rectangle",
            title: "Select Rectangle (".concat(hotkeysShortcuts.switchSelectTool, ")"),
            testId: "select-rectangle"
          }), jsx(Menu.Item, {
            itemId: "select-lasso",
            title: "Lasso selection (".concat(hotkeysShortcuts.switchSelectTool, ")"),
            testId: "select-lasso"
          }), jsx(Menu.Item, {
            itemId: "select-structure",
            title: "Structure Selection (".concat(hotkeysShortcuts.switchSelectTool, ")"),
            testId: "select-structure"
          })]
        })
      }), jsx(Menu.Item, {
        itemId: "erase",
        title: "Erase (".concat(hotkeysShortcuts.erase, ")"),
        testId: "erase",
        disabled: isSequenceMode
      })]
    }), jsx(Menu.Group, {
      children: jsxs(Menu.Submenu, {
        disabled: isSequenceMode,
        testId: "bonds-drop-down-button",
        needOpenByMenuItemClick: false,
        children: [jsx(Menu.Item, {
          itemId: "bond-single",
          title: "Single Bond (1)",
          testId: "single-bond",
          disabled: isSequenceMode
        }), jsx(Menu.Item, {
          itemId: "bond-hydrogen",
          title: "Hydrogen Bond (2)",
          testId: "hydrogen-bond",
          disabled: isSequenceMode
        })]
      })
    })]
  });
}
var ElementAndDropdown = createStyled("div", {
  target: "e1aw4j3q7"
} )({
  name: "bjn8wh",
  styles: "position:relative"
} );
var DropDownButton = createStyled(Button$1, {
  target: "e1aw4j3q6"
} )("display:flex;color:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.color.dropdown.primary;
}, ";padding-right:0;padding-left:0;& svg{margin-left:2px;width:1rem;height:1rem;}" + ("" ));
var ZoomLabel = createStyled("span", {
  target: "e1aw4j3q5"
} )({
  name: "td41hq",
  styles: "width:35px"
} );
var Dropdown = createStyled(Popover, {
  target: "e1aw4j3q4"
} )("& .MuiPopover-paper{padding:8px;width:175px;border:none;border-radius:0px 0px 4px 4px;box-shadow:", function(_ref22) {
  var theme = _ref22.theme;
  return theme.ketcher.shadow.regular;
}, ";box-sizing:border-box;}" + ("" ));
var DropDownContent = createStyled("div", {
  target: "e1aw4j3q3"
} )({
  name: "5s1n17",
  styles: "display:flex;flex-direction:column;white-space:nowrap;word-break:keep-all;background:white"
} );
var ZoomControlButton = createStyled(Button$1, {
  target: "e1aw4j3q2"
} )("display:flex;justify-content:space-between;font-size:", function(_ref3) {
  var theme = _ref3.theme;
  return theme.ketcher.font.size.regular;
}, ";line-height:14px;padding:7px 8px;text-transform:none;color:", function(_ref4) {
  var theme = _ref4.theme;
  return theme.ketcher.color.dropdown.primary;
}, ";" + ("" ));
var ShortcutLabel = createStyled("span", {
  target: "e1aw4j3q1"
} )({
  name: "btyqtq",
  styles: "color:#cad3dd"
} );
var StyledInput = createStyled("input", {
  target: "e1aw4j3q0"
} )("border:1px solid #cad3dd;border-radius:4px;padding:3px 8px;color:", function(_ref5) {
  var theme = _ref5.theme;
  return theme.ketcher.color.text.light;
}, ";font-size:", function(_ref6) {
  var theme = _ref6.theme;
  return theme.ketcher.font.size.medium;
}, ";line-height:16px;margin-bottom:8px;&:hover{border-color:", function(_ref7) {
  var theme = _ref7.theme;
  return theme.ketcher.color.input.border.hover;
}, ";}&:active,&:focus{border-color:", function(_ref8) {
  var theme = _ref8.theme;
  return theme.ketcher.outline.selected.color;
}, ";outline:none;}&::after,&::before{display:none;}" + ("" ));
var ZoomInput = function ZoomInput2(_ref3) {
  var onZoomSubmit = _ref3.onZoomSubmit, currentZoom = _ref3.currentZoom, inputRef = _ref3.inputRef;
  var onKeyDown = reactExports.useCallback(function(event) {
    var inputEl = inputRef.current;
    if (!inputEl) return;
    var zoomShortcuts = [hotkeysShortcuts["zoom-out"], hotkeysShortcuts["zoom-in"]];
    if (!zoomShortcuts.includes(event.key)) event.nativeEvent.stopImmediatePropagation();
    if (event.key === "Enter") {
      onZoomSubmit();
      inputEl.select();
    }
  }, [onZoomSubmit, inputRef, hotkeysShortcuts]);
  var onFocusHandler = function onFocusHandler2(event) {
    var el = event.target;
    el.select();
  };
  reactExports.useEffect(function() {
    var inputEl = inputRef.current;
    updateInputString(currentZoom, inputEl);
    if (document.activeElement === inputEl) {
      inputEl === null || inputEl === void 0 || inputEl.select();
    }
  }, [currentZoom, inputRef]);
  reactExports.useEffect(function() {
    var inputEl = inputRef.current;
    inputEl === null || inputEl === void 0 || inputEl.focus();
    inputEl === null || inputEl === void 0 || inputEl.select();
  }, [inputRef]);
  return jsx(StyledInput, {
    ref: inputRef,
    "data-testid": "zoom-value",
    onFocus: onFocusHandler,
    onKeyDown
  });
};
var ZoomControls = function ZoomControls2() {
  var _useState = reactExports.useState(false), _useState2 = _slicedToArray(_useState, 2), isExpanded = _useState2[0], setIsExpanded = _useState2[1];
  var _useState3 = reactExports.useState(100), _useState4 = _slicedToArray(_useState3, 2), currentZoom = _useState4[0], setCurrentZoom = _useState4[1];
  var containerRef = reactExports.useRef(null);
  var inputRef = reactExports.useRef(null);
  reactExports.useEffect(function() {
    var _ZoomTool$instance;
    ZoomTool === null || ZoomTool === void 0 || (_ZoomTool$instance = ZoomTool.instance) === null || _ZoomTool$instance === void 0 || _ZoomTool$instance.subscribeOnZoomEvent(function() {
      var _ZoomTool$instance2;
      setCurrentZoom(Math.round((ZoomTool === null || ZoomTool === void 0 || (_ZoomTool$instance2 = ZoomTool.instance) === null || _ZoomTool$instance2 === void 0 ? void 0 : _ZoomTool$instance2.getZoomLevel()) * 100));
    });
  }, [ZoomTool === null || ZoomTool === void 0 ? void 0 : ZoomTool.instance]);
  var onZoomSubmit = reactExports.useCallback(function() {
    var inputEl = inputRef.current;
    if (!inputEl) return;
    var userInput = getIntegerFromString(inputEl.value);
    if (userInput && userInput !== currentZoom) {
      var zoomToSet = getValidZoom(userInput, currentZoom);
      updateInputString(zoomToSet, inputEl);
      ZoomTool.instance.zoomTo(zoomToSet / 100);
    } else {
      updateInputString(currentZoom, inputEl);
    }
  }, [currentZoom]);
  var onClose = function onClose2() {
    setIsExpanded(false);
  };
  var onExpand = function onExpand2() {
    setIsExpanded(true);
  };
  var onZoomIn = function onZoomIn2() {
    ZoomTool.instance.zoomIn();
  };
  var onZoomOut = function onZoomOut2() {
    ZoomTool.instance.zoomOut();
  };
  var onZoomReset = function onZoomReset2() {
    ZoomTool.instance.resetZoom();
  };
  return jsxs(ElementAndDropdown, {
    ref: containerRef,
    children: [jsxs(DropDownButton, {
      onClick: onExpand,
      "data-testid": "zoom-selector",
      children: [jsxs(ZoomLabel, {
        "data-testid": "zoom-input",
        children: [currentZoom, "%"]
      }), jsx(Icon, {
        name: "chevron"
      })]
    }), jsx(Dropdown, {
      open: isExpanded,
      onClose,
      anchorEl: containerRef.current,
      container: document.querySelector(KETCHER_MACROMOLECULES_ROOT_NODE_SELECTOR),
      anchorOrigin: {
        vertical: "bottom",
        horizontal: "right"
      },
      transformOrigin: {
        vertical: "top",
        horizontal: "right"
      },
      children: jsxs(DropDownContent, {
        children: [jsx(ZoomInput, {
          onZoomSubmit,
          inputRef,
          currentZoom
        }), jsxs(ZoomControlButton, {
          "data-testid": "zoom-out",
          title: "Zoom Out",
          onClick: onZoomOut,
          children: [jsx("span", {
            children: "Zoom out"
          }), jsx(ShortcutLabel, {
            children: hotkeysShortcuts["zoom-minus"]
          })]
        }), jsxs(ZoomControlButton, {
          "data-testid": "zoom-in",
          title: "Zoom In",
          onClick: onZoomIn,
          children: [jsx("span", {
            children: "Zoom in"
          }), jsx(ShortcutLabel, {
            children: hotkeysShortcuts["zoom-plus"]
          })]
        }), jsxs(ZoomControlButton, {
          "data-testid": "zoom-default",
          title: "Zoom 100%",
          onClick: onZoomReset,
          children: [jsx("span", {
            children: "Zoom 100%"
          }), jsx(ShortcutLabel, {
            children: hotkeysShortcuts["zoom-reset"]
          })]
        })]
      })
    })]
  });
};
function ownKeys$2(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$2(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$2(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$2(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
var noPreviewTools = [ToolName.bondSingle, ToolName.selectRectangle];
var EditorEvents = function EditorEvents2() {
  var editor = useAppSelector(selectEditor);
  var activeTool = useAppSelector(selectEditorActiveTool);
  var isContextMenuActive = useAppSelector(selectIsContextMenuActive);
  var dispatch2 = useAppDispatch();
  var presets = useAppSelector(selectAllPresets);
  var hasAtLeastOneAntisense = useAppSelector(hasAntisenseChains);
  var lastSelectedSelectionMenuItem = useAppSelector(selectLastSelectedSelectionMenuItem);
  var handleMonomersLibraryUpdate = reactExports.useCallback(function() {
    dispatch2(loadMonomerLibrary2(editor === null || editor === void 0 ? void 0 : editor.monomersLibrary));
    dispatch2(loadDefaultPresets2(editor === null || editor === void 0 ? void 0 : editor.defaultRnaPresetsLibraryItems));
  }, [editor]);
  reactExports.useEffect(function() {
    editor === null || editor === void 0 || editor.events.updateMonomersLibrary.add(handleMonomersLibraryUpdate);
    return function() {
      editor === null || editor === void 0 || editor.events.updateMonomersLibrary.remove(handleMonomersLibraryUpdate);
    };
  }, [editor]);
  reactExports.useEffect(function() {
    var onSelectSelectionTool = function onSelectSelectionTool2() {
      editor === null || editor === void 0 || editor.events.selectTool.dispatch([lastSelectedSelectionMenuItem]);
      dispatch2(selectTool2(lastSelectedSelectionMenuItem));
    };
    if (editor) {
      editor.events.selectSelectionTool.add(onSelectSelectionTool);
    }
    return function() {
      editor === null || editor === void 0 || editor.events.selectSelectionTool.remove(onSelectSelectionTool);
    };
  }, [dispatch2, editor, lastSelectedSelectionMenuItem]);
  reactExports.useEffect(function() {
    var handler = function handler2(_ref3) {
      var _ref22 = _slicedToArray(_ref3, 1), toolName = _ref22[0];
      if (toolName !== activeTool) {
        dispatch2(selectTool2(toolName));
      }
    };
    if (editor) {
      editor.events.error.add(function(errorText) {
        dispatch2(openErrorTooltip2(errorText));
      });
      editor.events.openErrorModal.add(function(errorData) {
        dispatch2(openErrorModal2(errorData));
      });
      dispatch2(selectTool2("select-rectangle"));
      editor.events.selectTool.dispatch(["select-rectangle"]);
      editor.events.openMonomerConnectionModal.add(function(additionalProps) {
        return dispatch2(openModal2({
          name: "monomerConnection",
          additionalProps
        }));
      });
      editor.events.openConfirmationDialog.add(function(additionalProps) {
        return dispatch2(openModal2({
          name: "confirmationDialog",
          additionalProps
        }));
      });
      editor.events.selectTool.add(handler);
    }
    return function() {
      dispatch2(selectTool2(null));
      editor === null || editor === void 0 || editor.events.selectTool.remove(handler);
    };
  }, [editor]);
  var dispatchShowPreview = reactExports.useCallback(function(payload) {
    return dispatch2(showPreview2(payload));
  }, [dispatch2]);
  var debouncedShowPreview = reactExports.useCallback(lodashExports.debounce(function(p) {
    return dispatchShowPreview(p);
  }, 500), [dispatchShowPreview]);
  reactExports.useEffect(function() {
    var handler = function handler2(_ref3) {
      var _ref4 = _slicedToArray(_ref3, 1), toolName = _ref4[0];
      if (toolName !== activeTool) {
        dispatch2(selectTool2(toolName));
      }
    };
    if (editor) {
      editor.events.error.add(function(errorText) {
        dispatch2(openErrorTooltip2(errorText));
      });
      editor.events.openErrorModal.add(function(errorData) {
        dispatch2(openErrorModal2(errorData));
      });
      dispatch2(selectTool2("select-rectangle"));
      editor.events.selectTool.dispatch(["select-rectangle"]);
      editor.events.openMonomerConnectionModal.add(function(additionalProps) {
        return dispatch2(openModal2({
          name: "monomerConnection",
          additionalProps
        }));
      });
      editor.events.selectTool.add(handler);
    }
    return function() {
      dispatch2(selectTool2(null));
      editor === null || editor === void 0 || editor.events.selectTool.remove(handler);
    };
  }, [editor]);
  var handleOpenBondPreview = reactExports.useCallback(function(polymerBond, style) {
    var previewData = {
      type: PreviewType.Bond,
      polymerBond,
      style
    };
    debouncedShowPreview(previewData);
  }, [debouncedShowPreview]);
  var handleOpenPreview = reactExports.useCallback(function(e) {
    var _e$target$__data__, _e$target$__data__2, _e$target$__data__3;
    if (e.buttons === 1) {
      return;
    }
    if (e.buttons === 2) {
      return;
    }
    if (isContextMenuActive) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    var polymerBond = (_e$target$__data__ = e.target.__data__) === null || _e$target$__data__ === void 0 ? void 0 : _e$target$__data__.polymerBond;
    if (polymerBond && !polymerBond.finished || polymerBond instanceof HydrogenBond) {
      return;
    }
    if (polymerBond) {
      var style = calculateBondPreviewPosition(polymerBond, e.target.getBoundingClientRect());
      handleOpenBondPreview(polymerBond, style);
      return;
    }
    var sequenceNode = (_e$target$__data__2 = e.target.__data__) === null || _e$target$__data__2 === void 0 ? void 0 : _e$target$__data__2.node;
    var monomer = ((_e$target$__data__3 = e.target.__data__) === null || _e$target$__data__3 === void 0 ? void 0 : _e$target$__data__3.monomer) || (sequenceNode === null || sequenceNode === void 0 ? void 0 : sequenceNode.monomer);
    if (sequenceNode && sequenceNode instanceof BackBoneSequenceNode) {
      return;
    }
    if (monomer instanceof AmbiguousMonomer) {
      var ambiguousMonomerPreviewData = {
        type: PreviewType.AmbiguousMonomer,
        monomer: monomer.variantMonomerItem,
        target: e.target
      };
      debouncedShowPreview(ambiguousMonomerPreviewData);
      return;
    }
    var monomerItem = monomer.monomerItem;
    var attachmentPointsToBonds = _objectSpread$2({}, monomer.attachmentPointsToBonds);
    var isNucleotideOrNucleoside = sequenceNode instanceof Nucleotide || sequenceNode instanceof Nucleoside;
    if (sequenceNode instanceof LinkerSequenceNode) {
      var monomers = sequenceNode.monomers;
      if (monomers.length > 1) {
        var chemChainPreviewData = {
          type: PreviewType.Preset,
          monomers: monomers.map(function(m) {
            return m.monomerItem;
          }),
          position: PresetPosition.ChainMiddle,
          target: e.target
        };
        debouncedShowPreview(chemChainPreviewData);
        return;
      }
    }
    if (isNucleotideOrNucleoside) {
      var _sequenceNode$phospha;
      var _monomers = sequenceNode instanceof Nucleotide ? [sequenceNode.sugar.monomerItem, sequenceNode.rnaBase.monomerItem, (_sequenceNode$phospha = sequenceNode.phosphate) === null || _sequenceNode$phospha === void 0 ? void 0 : _sequenceNode$phospha.monomerItem] : [sequenceNode.sugar.monomerItem, sequenceNode.rnaBase.monomerItem];
      if (sequenceNode.rnaBase instanceof AmbiguousMonomer) {
        var _ambiguousMonomerPreviewData = {
          type: PreviewType.AmbiguousMonomer,
          monomer: sequenceNode.rnaBase.variantMonomerItem,
          presetMonomers: _monomers,
          target: e.target
        };
        debouncedShowPreview(_ambiguousMonomerPreviewData);
        return;
      }
      var existingPreset = presets.find(function(preset) {
        var presetMonomers = [preset.sugar, preset.base, preset.phosphate];
        return _monomers.every(function(monomer2, index) {
          var _presetMonomers$index;
          return (monomer2 === null || monomer2 === void 0 ? void 0 : monomer2.props.Name) === ((_presetMonomers$index = presetMonomers[index]) === null || _presetMonomers$index === void 0 ? void 0 : _presetMonomers$index.props.Name);
        });
      });
      var position;
      if (sequenceNode instanceof Nucleoside) {
        position = PresetPosition.ChainEnd;
      } else if (sequenceNode.firstMonomerInNode.R1AttachmentPoint !== void 0) {
        position = PresetPosition.ChainStart;
      } else {
        position = PresetPosition.ChainMiddle;
      }
      var presetPreviewData = {
        type: PreviewType.Preset,
        monomers: _monomers,
        name: existingPreset === null || existingPreset === void 0 ? void 0 : existingPreset.name,
        idtAliases: existingPreset === null || existingPreset === void 0 ? void 0 : existingPreset.idtAliases,
        aliasAxoLabs: existingPreset === null || existingPreset === void 0 ? void 0 : existingPreset.aliasAxoLabs,
        phosphatePosition: sequenceNode instanceof Nucleotide ? "right" : void 0,
        position,
        target: e.target
      };
      debouncedShowPreview(presetPreviewData);
      return;
    }
    var monomerPreviewData = {
      type: PreviewType.Monomer,
      monomer: monomerItem,
      attachmentPointsToBonds,
      target: e.target
    };
    debouncedShowPreview(monomerPreviewData);
  }, [handleOpenBondPreview, debouncedShowPreview, presets, isContextMenuActive]);
  var handleClosePreview = reactExports.useCallback(function() {
    debouncedShowPreview.cancel();
    dispatch2(showPreview2(void 0));
  }, [debouncedShowPreview, dispatch2]);
  reactExports.useEffect(function() {
    editor === null || editor === void 0 || editor.events.mouseOverMonomer.add(handleOpenPreview);
    editor === null || editor === void 0 || editor.events.mouseLeaveMonomer.add(handleClosePreview);
    editor === null || editor === void 0 || editor.events.mouseLeaveAttachmentPoint.add(handleClosePreview);
    editor === null || editor === void 0 || editor.events.mouseDownAttachmentPoint.add(handleClosePreview);
    editor === null || editor === void 0 || editor.events.mouseOverSequenceItem.add(handleOpenPreview);
    editor === null || editor === void 0 || editor.events.mouseLeaveSequenceItem.add(handleClosePreview);
    editor === null || editor === void 0 || editor.events.mouseOverPolymerBond.add(handleOpenPreview);
    editor === null || editor === void 0 || editor.events.mouseLeavePolymerBond.add(handleClosePreview);
    var onMoveHandler = function onMoveHandler2(e) {
      handleClosePreview();
      var isLeftClick = e.buttons === 1;
      if (!isLeftClick || !noPreviewTools.includes(activeTool)) {
        handleOpenPreview(e);
      }
    };
    editor === null || editor === void 0 || editor.events.mouseOnMoveMonomer.add(onMoveHandler);
    editor === null || editor === void 0 || editor.events.mouseMoveAttachmentPoint.add(onMoveHandler);
    editor === null || editor === void 0 || editor.events.mouseOnMoveSequenceItem.add(onMoveHandler);
    editor === null || editor === void 0 || editor.events.mouseOnMovePolymerBond.add(onMoveHandler);
    window.addEventListener("hidePreview", handleClosePreview);
    return function() {
      editor === null || editor === void 0 || editor.events.mouseOverMonomer.remove(handleOpenPreview);
      editor === null || editor === void 0 || editor.events.mouseLeaveMonomer.remove(handleClosePreview);
      editor === null || editor === void 0 || editor.events.mouseLeaveAttachmentPoint.remove(handleClosePreview);
      editor === null || editor === void 0 || editor.events.mouseOverSequenceItem.remove(handleOpenPreview);
      editor === null || editor === void 0 || editor.events.mouseLeaveSequenceItem.remove(handleClosePreview);
      editor === null || editor === void 0 || editor.events.mouseOverPolymerBond.remove(handleOpenPreview);
      editor === null || editor === void 0 || editor.events.mouseLeavePolymerBond.remove(handleClosePreview);
      editor === null || editor === void 0 || editor.events.mouseOnMoveMonomer.remove(onMoveHandler);
      editor === null || editor === void 0 || editor.events.mouseMoveAttachmentPoint.remove(onMoveHandler);
      editor === null || editor === void 0 || editor.events.mouseOnMoveSequenceItem.remove(onMoveHandler);
      editor === null || editor === void 0 || editor.events.mouseOnMovePolymerBond.remove(onMoveHandler);
      window.removeEventListener("hidePreview", handleClosePreview);
    };
  }, [editor, activeTool, handleOpenPreview, handleClosePreview]);
  reactExports.useEffect(function() {
    if (!hasAtLeastOneAntisense) {
      editor === null || editor === void 0 || editor.events.resetSequenceEditMode.dispatch();
    }
  }, [hasAtLeastOneAntisense]);
  return jsx(Fragment, {});
};
var SelectedMonomersContextMenu = function SelectedMonomersContextMenu2(_ref3) {
  var _selectedMonomers = _ref3.selectedMonomers, contextMenuEvent = _ref3.contextMenuEvent;
  var selectedMonomers = _selectedMonomers || [];
  var editor = useAppSelector(selectEditor);
  var _useContextMenu = Fe({
    id: CONTEXT_MENU_ID.FOR_SELECTED_MONOMERS
  }), hideAll = _useContextMenu.hideAll;
  var monomersForAminoAcidModification = getMonomersForAminoAcidModification(selectedMonomers, contextMenuEvent);
  var isCanvasContext = function isCanvasContext2(props) {
    var _editor$drawingEntiti, _editor$drawingEntiti2;
    var hasSelectedEntities = ((_editor$drawingEntiti = editor === null || editor === void 0 || (_editor$drawingEntiti2 = editor.drawingEntitiesManager) === null || _editor$drawingEntiti2 === void 0 || (_editor$drawingEntiti2 = _editor$drawingEntiti2.selectedEntitiesArr) === null || _editor$drawingEntiti2 === void 0 ? void 0 : _editor$drawingEntiti2.length) !== null && _editor$drawingEntiti !== void 0 ? _editor$drawingEntiti : 0) > 0;
    return !(props !== null && props !== void 0 && props.polymerBondRenderer) && (!(props !== null && props !== void 0 && props.selectedMonomers) || (props === null || props === void 0 ? void 0 : props.selectedMonomers.length) === 0) && !hasSelectedEntities;
  };
  var modifyAminoAcidsMenuItems = getModifyAminoAcidsMenuItems(monomersForAminoAcidModification);
  var isBondContext = function isBondContext2(props) {
    return !!(props !== null && props !== void 0 && props.polymerBondRenderer);
  };
  var isAntisenseBlockVisible = selectedMonomers && selectedMonomers.length > 0 && isAntisenseOptionVisible(selectedMonomers);
  var isFlexMode = (editor === null || editor === void 0 ? void 0 : editor.mode.modeName) === "flex-layout-mode";
  var cyclicStructureFormationDisabled = !isFlexMode || (editor === null || editor === void 0 ? void 0 : editor.drawingEntitiesManager.selectedMicromoleculeEntities.length) > 0 || !isCycleExistsForSelectedMonomers(selectedMonomers);
  var menuItems = [{
    name: "copy",
    title: "Copy",
    icon: jsx(Icon, {
      name: "copyMenu"
    }),
    disabled: function disabled(_ref22) {
      var _ref2$props = _ref22.props, props = _ref2$props === void 0 ? {} : _ref2$props;
      return isBondContext(props) || isCanvasContext(props);
    }
  }, {
    name: SequenceItemContextMenuNames.paste,
    title: "Paste",
    icon: jsx(Icon, {
      name: "pasteNavBar"
    }),
    disabled: function disabled(_ref32) {
      var _ref3$props = _ref32.props, props = _ref3$props === void 0 ? {} : _ref3$props;
      return !isCanvasContext(props);
    },
    separator: true
  }, {
    name: "create_antisense_rna_chain",
    title: "Create Antisense RNA Strand",
    separator: false,
    disabled: isAntisenseCreationDisabled(selectedMonomers),
    hidden: function hidden(_ref4) {
      var props = _ref4.props;
      return !(props !== null && props !== void 0 && props.selectedMonomers) || !isAntisenseOptionVisible(props === null || props === void 0 ? void 0 : props.selectedMonomers);
    }
  }, {
    name: "create_antisense_dna_chain",
    title: "Create Antisense DNA Strand",
    disabled: isAntisenseCreationDisabled(selectedMonomers),
    hidden: function hidden(_ref5) {
      var props = _ref5.props;
      return !(props !== null && props !== void 0 && props.selectedMonomers) || !isAntisenseOptionVisible(props === null || props === void 0 ? void 0 : props.selectedMonomers);
    },
    separator: isAntisenseBlockVisible
  }, {
    name: SequenceItemContextMenuNames.modifyAminoAcids,
    title: "Modify amino acids",
    disabled: false,
    hidden: !modifyAminoAcidsMenuItems.length,
    subMenuItems: modifyAminoAcidsMenuItems
  }, {
    name: "layout_circular",
    title: "Arrange as a Ring",
    disabled: cyclicStructureFormationDisabled,
    hidden: !isFlexMode
  }, {
    name: "edit_attachment_points",
    title: "Edit Attachment Points...",
    disabled: function disabled(_ref6) {
      var props = _ref6.props;
      return !isBondContext(props);
    },
    separator: true
  }, {
    name: "delete",
    title: "Delete",
    icon: jsx(Icon, {
      name: "deleteMenu"
    }),
    disabled: function disabled(_ref7) {
      var _ref7$props = _ref7.props, props = _ref7$props === void 0 ? {} : _ref7$props;
      return isCanvasContext(props);
    }
  }];
  var handleMenuChange = function handleMenuChange2(_ref8) {
    var menuItemId = _ref8.id, props = _ref8.props;
    switch (true) {
      case menuItemId === "layout_circular":
        editor === null || editor === void 0 || editor.events.layoutCircular.dispatch();
        hideAll();
        break;
      case menuItemId === "copy":
        editor === null || editor === void 0 || editor.events.copySelectedStructure.dispatch();
        break;
      case menuItemId === "create_antisense_rna_chain":
        editor === null || editor === void 0 || editor.events.createAntisenseChain.dispatch(false);
        break;
      case menuItemId === "create_antisense_dna_chain":
        editor === null || editor === void 0 || editor.events.createAntisenseChain.dispatch(true);
        break;
      case menuItemId === "delete":
        editor === null || editor === void 0 || editor.events.deleteSelectedStructure.dispatch();
        break;
      case menuItemId === "paste":
        editor === null || editor === void 0 || editor.events.pasteFromClipboard.dispatch();
        break;
      case menuItemId === "edit_attachment_points": {
        var _props$polymerBondRen;
        var polymerBond = props === null || props === void 0 || (_props$polymerBondRen = props.polymerBondRenderer) === null || _props$polymerBondRen === void 0 ? void 0 : _props$polymerBondRen.polymerBond;
        if (!polymerBond) return;
        editor === null || editor === void 0 || editor.events.openMonomerConnectionModal.dispatch({
          firstMonomer: polymerBond.firstMonomer,
          secondMonomer: polymerBond.secondMonomer,
          polymerBond,
          isReconnectionDialog: true
        });
        break;
      }
      case (menuItemId === null || menuItemId === void 0 ? void 0 : menuItemId.startsWith(AMINO_ACID_MODIFICATION_MENU_ITEM_PREFIX)): {
        var modificationType = menuItemId === null || menuItemId === void 0 ? void 0 : menuItemId.replace(AMINO_ACID_MODIFICATION_MENU_ITEM_PREFIX, "");
        editor === null || editor === void 0 || editor.events.modifyAminoAcids.dispatch({
          monomers: monomersForAminoAcidModification,
          modificationType
        });
        break;
      }
    }
  };
  var ketcherEditorRootElement = document.querySelector(KETCHER_MACROMOLECULES_ROOT_NODE_SELECTOR);
  return ketcherEditorRootElement && reactDomExports.createPortal(jsx(ContextMenu, {
    id: CONTEXT_MENU_ID.FOR_SELECTED_MONOMERS,
    handleMenuChange,
    menuItems
  }), ketcherEditorRootElement);
};
var StyledButton = createStyled(Button, {
  target: "e1846tr80"
} )(function(_ref3) {
  var theme = _ref3.theme, isActive = _ref3.isActive;
  return {
    width: "40px",
    height: "31px",
    backgroundColor: isActive ? theme.ketcher.color.button.group.active : "white",
    marginRight: "8px",
    border: isActive ? theme.ketcher.outline.selected.color : theme.ketcher.outline.small,
    borderRadius: "4px",
    outline: "none",
    ":hover": {
      backgroundColor: isActive ? theme.ketcher.color.button.group.hover : "white"
    },
    ":hover svg": {
      fill: isActive ? "white" : theme.ketcher.color.button.group.active
    }
  };
}, "" );
var SequenceSyncEditModeButton = function SequenceSyncEditModeButton2() {
  var editor = useAppSelector(selectEditor);
  var _useState = reactExports.useState(true), _useState2 = _slicedToArray(_useState, 2), isSequenceSyncEditMode = _useState2[0], setIsSequenceSyncEditMode = _useState2[1];
  var isSequenceMode = useLayoutMode() === "sequence-layout-mode";
  var hasAtLeastOneAntisense = useAppSelector(hasAntisenseChains);
  var handleClick = function handleClick2() {
    var isSequenceSyncEditModeNewState = !isSequenceSyncEditMode;
    setIsSequenceSyncEditMode(isSequenceSyncEditModeNewState);
    editor === null || editor === void 0 || editor.events.toggleIsSequenceSyncEditMode.dispatch(isSequenceSyncEditModeNewState);
    blurActiveElement();
  };
  reactExports.useEffect(function() {
    if (isSequenceMode && hasAtLeastOneAntisense) {
      editor === null || editor === void 0 || editor.events.toggleIsSequenceSyncEditMode.dispatch(isSequenceSyncEditMode);
    }
  }, [isSequenceMode, hasAtLeastOneAntisense]);
  return isSequenceMode && hasAtLeastOneAntisense ? jsx(StyledButton, {
    isActive: isSequenceSyncEditMode,
    onClick: handleClick,
    "data-testid": "sync_sequence_edit_mode",
    "data-isactive": isSequenceSyncEditMode,
    children: jsxs("svg", {
      width: "24",
      height: "24",
      viewBox: "0 0 24 24",
      xmlns: "http://www.w3.org/2000/svg",
      fill: isSequenceSyncEditMode ? "white" : "#333333",
      children: [jsx("rect", {
        x: "1",
        y: "1.5",
        width: "22",
        height: "2",
        rx: "1"
      }), jsx("rect", {
        x: "2.5",
        y: "1.5",
        width: "5",
        height: "1.5",
        rx: "0.75",
        transform: "rotate(90 2.5 1.5)"
      }), jsx("rect", {
        x: "9.33333",
        y: "1.5",
        width: "5",
        height: "1.5",
        rx: "0.75",
        transform: "rotate(90 9.33333 1.5)"
      }), jsx("rect", {
        x: "16.1667",
        y: "1.5",
        width: "5",
        height: "1.5",
        rx: "0.75",
        transform: "rotate(90 16.1667 1.5)"
      }), jsx("rect", {
        x: "23",
        y: "1.5",
        width: "5",
        height: "1.5",
        rx: "0.75",
        transform: "rotate(90 23 1.5)"
      }), jsx("path", {
        d: "M2.16873 14.2715C2.08963 14.3652 2.02518 14.4253 1.97537 14.4517C1.9285 14.478 1.8699 14.4912 1.79959 14.4912C1.66189 14.4912 1.55057 14.4458 1.46561 14.355C1.38357 14.2612 1.34256 14.1074 1.34256 13.8936V13.2871C1.34256 13.0703 1.38357 12.9165 1.46561 12.8257C1.55057 12.7319 1.66189 12.6851 1.79959 12.6851C1.90506 12.6851 1.99295 12.7129 2.06326 12.7686C2.1365 12.8242 2.19217 12.918 2.23025 13.0498C2.26834 13.1787 2.30789 13.2666 2.34891 13.3135C2.43387 13.4043 2.58475 13.4966 2.80154 13.5903C3.01834 13.6841 3.25564 13.731 3.51346 13.731C3.91482 13.731 4.24441 13.6372 4.50223 13.4497C4.66629 13.3354 4.74832 13.1948 4.74832 13.0278C4.74832 12.9165 4.70877 12.8125 4.62967 12.7158C4.55057 12.6162 4.42166 12.5342 4.24295 12.4697C4.12576 12.4258 3.86355 12.3657 3.45633 12.2896C2.96414 12.1987 2.59207 12.0889 2.34012 11.96C2.08816 11.8311 1.88895 11.6494 1.74246 11.415C1.59598 11.1807 1.52273 10.9272 1.52273 10.6548C1.52273 10.2241 1.70291 9.84766 2.06326 9.52539C2.42361 9.2002 2.89236 9.0376 3.46951 9.0376C3.70096 9.0376 3.91482 9.06396 4.11111 9.1167C4.31033 9.1665 4.49051 9.24414 4.65164 9.34961C4.76883 9.23535 4.88602 9.17822 5.0032 9.17822C5.13504 9.17822 5.24197 9.2251 5.324 9.31885C5.40897 9.40967 5.45145 9.56201 5.45145 9.77588V10.4526C5.45145 10.6694 5.40897 10.8247 5.324 10.9185C5.24197 11.0093 5.13504 11.0547 5.0032 11.0547C4.89188 11.0547 4.7952 11.021 4.71316 10.9536C4.64871 10.9038 4.60037 10.8042 4.56814 10.6548C4.53592 10.5054 4.4949 10.3984 4.4451 10.334C4.36014 10.2227 4.2327 10.1289 4.06277 10.0527C3.89285 9.97656 3.69656 9.93848 3.47391 9.93848C3.14871 9.93848 2.8909 10.0146 2.70047 10.167C2.51297 10.3164 2.41922 10.4731 2.41922 10.6372C2.41922 10.7485 2.4573 10.8569 2.53348 10.9624C2.61258 11.0649 2.72684 11.1455 2.87625 11.2041C2.97586 11.2451 3.25564 11.311 3.71561 11.4019C4.1785 11.4927 4.53299 11.5923 4.77908 11.7007C5.02811 11.8091 5.23465 11.979 5.39871 12.2104C5.56277 12.4419 5.6448 12.7173 5.6448 13.0366C5.6448 13.4819 5.48807 13.8379 5.17459 14.1045C4.75857 14.4561 4.2283 14.6318 3.58377 14.6318C3.33475 14.6318 3.09158 14.6011 2.85428 14.5396C2.6199 14.481 2.39139 14.3916 2.16873 14.2715ZM9.615 12.2632V13.5991H10.2214C10.4382 13.5991 10.5921 13.6416 10.6829 13.7266C10.7766 13.8086 10.8235 13.917 10.8235 14.0518C10.8235 14.1836 10.7766 14.292 10.6829 14.377C10.5921 14.459 10.4382 14.5 10.2214 14.5H8.10768C7.89381 14.5 7.74 14.459 7.64625 14.377C7.55543 14.292 7.51002 14.1821 7.51002 14.0474C7.51002 13.9155 7.55543 13.8086 7.64625 13.7266C7.74 13.6416 7.89381 13.5991 8.10768 13.5991H8.71412V12.2632L7.22438 10.0747C7.02516 10.0747 6.87867 10.0322 6.78492 9.94727C6.6941 9.8623 6.64869 9.75391 6.64869 9.62207C6.64869 9.4873 6.6941 9.37891 6.78492 9.29688C6.87867 9.21191 7.03395 9.16943 7.25074 9.16943L8.06813 9.17383C8.28492 9.17383 8.43873 9.21484 8.52955 9.29688C8.6233 9.37891 8.67018 9.4873 8.67018 9.62207C8.67018 9.82422 8.55152 9.9751 8.31422 10.0747L9.16676 11.3315L10.0017 10.0747C9.86988 10.0249 9.77613 9.96191 9.72047 9.88574C9.6648 9.80957 9.63697 9.72168 9.63697 9.62207C9.63697 9.4873 9.68238 9.37891 9.7732 9.29688C9.86695 9.21484 10.0222 9.17236 10.239 9.16943L11.0872 9.17383C11.304 9.17383 11.4578 9.21484 11.5486 9.29688C11.6423 9.37891 11.6892 9.4873 11.6892 9.62207C11.6892 9.75684 11.6423 9.8667 11.5486 9.95166C11.4548 10.0337 11.3025 10.0747 11.0916 10.0747L9.615 12.2632ZM13.7082 10.8745V13.5991H14.0334C14.2502 13.5991 14.404 13.6416 14.4949 13.7266C14.5886 13.8086 14.6355 13.917 14.6355 14.0518C14.6355 14.1836 14.5886 14.292 14.4949 14.377C14.404 14.459 14.2502 14.5 14.0334 14.5H12.8513C12.6345 14.5 12.4792 14.459 12.3855 14.377C12.2947 14.292 12.2493 14.1821 12.2493 14.0474C12.2493 13.9185 12.2947 13.8115 12.3855 13.7266C12.4763 13.6416 12.6169 13.5991 12.8074 13.5991V10.0747H12.6667C12.4499 10.0747 12.2947 10.0337 12.2009 9.95166C12.1101 9.8667 12.0647 9.75684 12.0647 9.62207C12.0647 9.4873 12.1101 9.37891 12.2009 9.29688C12.2947 9.21191 12.4499 9.16943 12.6667 9.16943L13.7082 9.17383L16.011 12.7861V10.0747H15.6858C15.469 10.0747 15.3137 10.0337 15.22 9.95166C15.1291 9.8667 15.0837 9.75684 15.0837 9.62207C15.0837 9.4873 15.1291 9.37891 15.22 9.29688C15.3137 9.21191 15.469 9.16943 15.6858 9.16943L16.8679 9.17383C17.0847 9.17383 17.2385 9.21484 17.3293 9.29688C17.4231 9.37891 17.47 9.4873 17.47 9.62207C17.47 9.75391 17.4246 9.8623 17.3337 9.94727C17.2429 10.0322 17.1038 10.0747 16.9163 10.0747V14.5H16.0242L13.7082 10.8745ZM21.9236 9.40234C21.9792 9.32617 22.0393 9.26904 22.1037 9.23096C22.1711 9.19287 22.2429 9.17383 22.3191 9.17383C22.4509 9.17383 22.5578 9.21924 22.6399 9.31006C22.7248 9.40088 22.7673 9.55469 22.7673 9.77148V10.5361C22.7673 10.7529 22.7248 10.9082 22.6399 11.002C22.5578 11.0928 22.4509 11.1382 22.3191 11.1382C22.1989 11.1382 22.1023 11.1045 22.029 11.0371C21.9558 10.9697 21.9016 10.8438 21.8664 10.6592C21.8459 10.5361 21.8049 10.4409 21.7434 10.3735C21.6233 10.2417 21.4548 10.1362 21.238 10.0571C21.0241 9.97803 20.8088 9.93848 20.592 9.93848C20.3225 9.93848 20.0749 9.99707 19.8493 10.1143C19.6237 10.2314 19.4245 10.4219 19.2517 10.6855C19.0788 10.9492 18.9924 11.2627 18.9924 11.626V12.2104C18.9924 12.644 19.1491 13.0059 19.4626 13.2959C19.779 13.5859 20.217 13.731 20.7766 13.731C21.1106 13.731 21.3933 13.6855 21.6247 13.5947C21.7595 13.542 21.903 13.438 22.0554 13.2827C22.1491 13.189 22.2224 13.1289 22.2751 13.1025C22.3279 13.0732 22.3879 13.0586 22.4553 13.0586C22.5754 13.0586 22.6809 13.104 22.7717 13.1948C22.8625 13.2856 22.9079 13.3926 22.9079 13.5156C22.9079 13.6387 22.8464 13.7705 22.7234 13.9111C22.5446 14.1162 22.3147 14.2773 22.0334 14.3945C21.6555 14.5527 21.238 14.6318 20.781 14.6318C20.2478 14.6318 19.7673 14.522 19.3396 14.3022C18.9939 14.1265 18.6994 13.8496 18.4563 13.4717C18.2131 13.0908 18.0915 12.6763 18.0915 12.228V11.6172C18.0915 11.1484 18.1999 10.7119 18.4167 10.3076C18.6364 9.90039 18.9397 9.58691 19.3264 9.36719C19.7131 9.14746 20.1233 9.0376 20.5569 9.0376C20.8176 9.0376 21.0608 9.06836 21.2863 9.12988C21.5149 9.18848 21.7273 9.2793 21.9236 9.40234Z"
      }), jsx("rect", {
        x: "23",
        y: "22.5",
        width: "22",
        height: "2",
        rx: "1",
        transform: "rotate(-180 23 22.5)"
      }), jsx("rect", {
        x: "21.5",
        y: "22.5",
        width: "5",
        height: "1.5",
        rx: "0.75",
        transform: "rotate(-90 21.5 22.5)"
      }), jsx("rect", {
        x: "14.6667",
        y: "22.5",
        width: "5",
        height: "1.5",
        rx: "0.75",
        transform: "rotate(-90 14.6667 22.5)"
      }), jsx("rect", {
        x: "7.83333",
        y: "22.5",
        width: "5",
        height: "1.5",
        rx: "0.75",
        transform: "rotate(-90 7.83333 22.5)"
      }), jsx("rect", {
        x: "1",
        y: "22.5",
        width: "5",
        height: "1.5",
        rx: "0.75",
        transform: "rotate(-90 1 22.5)"
      })]
    })
  }) : null;
};
var useTranslateAlongXAxis = function useTranslateAlongXAxis2(ref, offsetX) {
  var animateRef = reactExports.useRef(null);
  reactExports.useLayoutEffect(function() {
    var element = ref.current;
    if (!element) {
      return;
    }
    animateRef.current = requestAnimationFrame(function() {
      element.style.transform = "translateX(".concat(offsetX, "px)");
    });
    return function() {
      if (animateRef.current) {
        cancelAnimationFrame(animateRef.current);
        animateRef.current = null;
      }
    };
  }, [ref, offsetX]);
};
var useTranslateAlongXAxis$1 = useTranslateAlongXAxis;
var styles$1 = { "rulerArea": "RulerArea-module_rulerArea__Kix1O", "rulerInput": "RulerArea-module_rulerInput__nCNOa", "rulerInputDragging": "RulerArea-module_rulerInputDragging__saoOk", "rulerScale": "RulerArea-module_rulerScale__4YOKH", "rulerHandle": "RulerArea-module_rulerHandle__g4GPl" };
var RulerInput = function RulerInput2(_ref3) {
  var lineLengthValue = _ref3.lineLengthValue, offsetX = _ref3.offsetX, isDragging = _ref3.isDragging, layoutMode = _ref3.layoutMode, onCommitValue = _ref3.onCommitValue;
  var ref = reactExports.useRef(null);
  useTranslateAlongXAxis$1(ref, offsetX);
  var stringifiedLineLengthValue = lineLengthValue.toString();
  var _useState = reactExports.useState(null), _useState2 = _slicedToArray(_useState, 2), editingValue = _useState2[0], setEditingValue = _useState2[1];
  var displayValue = editingValue !== null ? editingValue : stringifiedLineLengthValue;
  var handleChange = function handleChange2(event) {
    setEditingValue(event.target.value);
  };
  var handleBlur = function handleBlur2() {
    if (!editingValue || editingValue.trim() === "") {
      setEditingValue(null);
      return;
    }
    var newValue = Number(editingValue);
    if (Number.isNaN(newValue) || newValue < 1) {
      setEditingValue(null);
      return;
    }
    var newLineLength = layoutMode === "sequence-layout-mode" ? Math.round(newValue / 10) * 10 : newValue;
    setEditingValue(null);
    onCommitValue(newLineLength);
  };
  var handleKeyDown = function handleKeyDown2(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      event.currentTarget.blur();
    }
  };
  return jsx("input", {
    className: clsx$2(styles$1.rulerInput, isDragging && styles$1.rulerInputDragging),
    title: "Number of monomers in a line",
    type: "text",
    inputMode: "numeric",
    pattern: "[0-9]*",
    value: displayValue,
    onChange: handleChange,
    onBlur: handleBlur,
    onKeyDown: handleKeyDown,
    "data-testid": "ruler-input",
    disabled: isDragging,
    ref
  });
};
var RulerInput$1 = reactExports.memo(RulerInput);
var SequenceModeStartOffset = 40;
var SequenceModeItemWidth = 20;
var SequenceModeIndentWidth = 10;
var SnakeModeStartOffset = 25;
var SnakeModeItemWidth = SnakeLayoutCellWidth;
var RulerScale = function RulerScale2(_ref3) {
  var transform = _ref3.transform, layoutMode = _ref3.layoutMode;
  _ref3.lineLengthValue;
  var ref = reactExports.useRef(null);
  var isZoomedOut = transform.k - 0.5 < Number.EPSILON;
  var getDynamicPositions = function getDynamicPositions2(visibleStart, visibleEnd, step, offset) {
    var startIndex = Math.max(0, Math.floor((visibleStart - offset) / step));
    var endIndex = Math.ceil((visibleEnd - offset) / step) + 10;
    return Array.from({
      length: endIndex - startIndex
    }, function(_2, i) {
      return offset + (startIndex + i) * step;
    });
  };
  var positions = reactExports.useMemo(function() {
    var _ref$current;
    var canvasWidth = ((_ref$current = ref.current) === null || _ref$current === void 0 || (_ref$current = _ref$current.ownerSVGElement) === null || _ref$current === void 0 ? void 0 : _ref$current.width.baseVal.value) || 1e3;
    var visibleStart = transform.invertX(0);
    var visibleEnd = transform.invertX(canvasWidth);
    if (layoutMode === "sequence-layout-mode") {
      var step = 10 * SequenceModeItemWidth + SequenceModeIndentWidth;
      return getDynamicPositions(visibleStart, visibleEnd, step, SequenceModeStartOffset);
    }
    if (layoutMode === "snake-layout-mode") {
      return getDynamicPositions(visibleStart, visibleEnd, SnakeModeItemWidth, SnakeModeStartOffset);
    }
    return [];
  }, [layoutMode, transform]);
  var svgChildren = reactExports.useMemo(function() {
    var children2 = [];
    positions.forEach(function(position, i) {
      if (layoutMode === "sequence-layout-mode") {
        children2.push(jsx("line", {
          x1: transform.applyX(position),
          y1: 14,
          x2: transform.applyX(position),
          y2: 22,
          stroke: "#7C7C7F",
          strokeWidth: 1
        }, "ruler-mark-".concat(position)));
      } else if (layoutMode === "snake-layout-mode") {
        if (isZoomedOut) {
          var isMultipleOfFive = i % 5 === 0;
          if (isMultipleOfFive) {
            children2.push(jsx("text", {
              x: transform.applyX(position),
              y: 18,
              fontSize: 10,
              fontWeight: 500,
              fill: "#7C7C7F",
              textAnchor: "middle",
              dominantBaseline: "middle",
              children: i
            }, "ruler-label-".concat(position)));
          } else {
            children2.push(jsx("line", {
              x1: transform.applyX(position),
              y1: 14,
              x2: transform.applyX(position),
              y2: 22,
              stroke: "#7C7C7F",
              strokeWidth: 1
            }, "ruler-mark-".concat(position)));
          }
        } else {
          children2.push(jsx("text", {
            x: transform.applyX(position),
            y: 18,
            fontSize: 10,
            fontWeight: 500,
            fill: "#7C7C7F",
            textAnchor: "middle",
            dominantBaseline: "middle",
            children: i
          }, "ruler-label-".concat(position)));
        }
      }
      var nextPosition = positions[i + 1];
      if (nextPosition === void 0) {
        return;
      }
      if (isZoomedOut && layoutMode === "snake-layout-mode") {
        return;
      }
      children2.push(jsx("line", {
        x1: transform.applyX(position + 10),
        y1: 18,
        x2: transform.applyX(nextPosition - 10),
        y2: 18,
        stroke: "#B4B9D6",
        strokeDasharray: "2,2",
        strokeWidth: 1
      }, "ruler-fill-".concat(position, "-").concat(nextPosition)));
    });
    return children2;
  }, [positions, layoutMode, transform, isZoomedOut]);
  return jsx("svg", {
    className: styles$1.rulerScale,
    ref,
    "data-testid": "ruler-scale",
    children: svgChildren
  });
};
var RulerScale$1 = reactExports.memo(RulerScale);
var RulerHandle = function RulerHandle2(_ref3) {
  var offsetX = _ref3.offsetX, onDragStart = _ref3.onDragStart, onDrag = _ref3.onDrag, onDragEnd = _ref3.onDragEnd;
  var svgRef = reactExports.useRef(null);
  var handleRef = reactExports.useRef(null);
  useTranslateAlongXAxis$1(svgRef, offsetX);
  reactExports.useEffect(function() {
    if (!handleRef.current) {
      return;
    }
    var handle = select(handleRef.current);
    var dragBehavior = drag().on("start", onDragStart).on("drag", onDrag).on("end", onDragEnd);
    handle.call(dragBehavior);
    return function() {
      handle.on(".drag", null);
    };
  }, [onDrag, onDragEnd, onDragStart]);
  return jsx("svg", {
    xmlns: "http://www.w3.org/2000/svg",
    className: styles$1.rulerHandle,
    viewBox: "0 0 16 13",
    fill: "none",
    pointerEvents: "none",
    ref: svgRef,
    "data-testid": "ruler-handle",
    children: jsxs("g", {
      cursor: "pointer",
      pointerEvents: "all",
      ref: handleRef,
      children: [jsx("mask", {
        id: "ruler-handle-mask",
        fill: "#fff",
        children: jsx("path", {
          fillRule: "evenodd",
          d: "M16 1.625a1 1 0 0 0-1-1H1a1 1 0 0 0-1 1v4.5a1 1 0 0 0 .4.8l7 5.25a1 1 0 0 0 1.2 0l7-5.25a1 1 0 0 0 .4-.8v-4.5Z",
          clipRule: "evenodd"
        })
      }), jsx("path", {
        fill: "#CAD3DD",
        fillRule: "evenodd",
        d: "M16 1.625a1 1 0 0 0-1-1H1a1 1 0 0 0-1 1v4.5a1 1 0 0 0 .4.8l7 5.25a1 1 0 0 0 1.2 0l7-5.25a1 1 0 0 0 .4-.8v-4.5Z",
        clipRule: "evenodd"
      }), jsx("path", {
        fill: "#B4B9D6",
        d: "m15.6 6.925-.6-.8.6.8Zm-8.2 5.25.6-.8-.6.8Zm-7-5.25.6-.8-.6.8Zm.6-5.3h14v-2H1v2Zm0 4.5v-4.5h-2v4.5h2Zm7 5.25-7-5.25-1.2 1.6 7 5.25 1.2-1.6Zm7-5.25-7 5.25 1.2 1.6 7-5.25-1.2-1.6Zm0-4.5v4.5h2v-4.5h-2Zm1.2 6.1a2 2 0 0 0 .8-1.6h-2l1.2 1.6Zm-9.4 5.25a2 2 0 0 0 2.4 0l-1.2-1.6-1.2 1.6ZM-1 6.125a2 2 0 0 0 .8 1.6l1.2-1.6h-2Zm16-4.5h2a2 2 0 0 0-2-2v2Zm-14-2a2 2 0 0 0-2 2h2v-2Z",
        mask: "url(#ruler-handle-mask)"
      })]
    })
  });
};
var RulerHandle$1 = reactExports.memo(RulerHandle);
var useZoomTransform = function useZoomTransform2() {
  var _useState = reactExports.useState(new Transform(1, 0, 0)), _useState2 = _slicedToArray(_useState, 2), transform = _useState2[0], setTransform = _useState2[1];
  reactExports.useEffect(function() {
    var zoom = ZoomTool.instance;
    if (!zoom) {
      return;
    }
    var zoomEventHandler = function zoomEventHandler2(transform2) {
      if (!transform2) {
        return;
      }
      requestAnimationFrame(function() {
        setTransform(transform2);
      });
    };
    zoom.subscribeOnZoomEvent(zoomEventHandler);
    return function() {
      zoom.unsubscribeOnZoomEvent(zoomEventHandler);
    };
  }, [ZoomTool.instance]);
  return transform;
};
var RulerArea = function RulerArea2() {
  var _editor$events, _editor$events2, _editor$events3;
  var layoutMode = useLayoutMode();
  var editorLineLength = useSelector(selectEditorLineLength);
  var lineLengthValue = editorLineLength[layoutMode];
  var editor = useSelector(selectEditor);
  var dragStartX = reactExports.useRef(0);
  var _useState = reactExports.useState(0), _useState2 = _slicedToArray(_useState, 2), dragDelta = _useState2[0], setDragDelta = _useState2[1];
  var _useState3 = reactExports.useState(false), _useState4 = _slicedToArray(_useState3, 2), isDragging = _useState4[0], setIsDragging3 = _useState4[1];
  var transform = useZoomTransform();
  var indentsInSequenceMode = lineLengthValue / 10 - 1;
  var translateValue = reactExports.useMemo(function() {
    if (layoutMode === "sequence-layout-mode") {
      var step = 10 * SequenceModeItemWidth + SequenceModeIndentWidth;
      var index = Math.floor(lineLengthValue / 10);
      return SequenceModeStartOffset + index * step;
    }
    if (layoutMode === "snake-layout-mode") {
      return SnakeModeStartOffset + lineLengthValue * SnakeModeItemWidth;
    }
    return 0;
  }, [layoutMode, lineLengthValue]);
  var _useMemo = reactExports.useMemo(function() {
    var translateValueWithZoomAndDrag = transform.applyX(translateValue) + dragDelta;
    var handlePosition = translateValueWithZoomAndDrag - 8;
    var inputPosition = translateValueWithZoomAndDrag + 10;
    var canvasWidth = editor === null || editor === void 0 ? void 0 : editor.canvas.width.baseVal.value;
    if (!canvasWidth) {
      return [inputPosition, handlePosition];
    }
    var canvasContainer = editor === null || editor === void 0 ? void 0 : editor.canvas.parentElement;
    var scrollLeft = (canvasContainer === null || canvasContainer === void 0 ? void 0 : canvasContainer.scrollLeft) || 0;
    var visibleLeftEdge = scrollLeft;
    var visibleRightEdge = scrollLeft + ((canvasContainer === null || canvasContainer === void 0 ? void 0 : canvasContainer.clientWidth) || canvasWidth);
    if (inputPosition + 35 > visibleRightEdge) {
      inputPosition = visibleRightEdge - 35;
    }
    if (inputPosition < visibleLeftEdge) {
      inputPosition = visibleLeftEdge;
    }
    return [inputPosition, handlePosition];
  }, [editor === null || editor === void 0 ? void 0 : editor.canvas.width.baseVal.value, editor === null || editor === void 0 ? void 0 : editor.canvas.parentElement, transform, translateValue, dragDelta]), _useMemo2 = _slicedToArray(_useMemo, 2), inputOffsetX = _useMemo2[0], handleOffsetX = _useMemo2[1];
  var updateSettings = reactExports.useCallback(function(value) {
    editor === null || editor === void 0 || editor.events.setEditorLineLength.dispatch(_defineProperty$1({}, layoutMode, value));
  }, [editor === null || editor === void 0 || (_editor$events = editor.events) === null || _editor$events === void 0 ? void 0 : _editor$events.setEditorLineLength, layoutMode]);
  var calculateLineLength = reactExports.useCallback(function(position) {
    if (layoutMode === "sequence-layout-mode") {
      var rawCount = (position - indentsInSequenceMode * SequenceModeIndentWidth - SequenceModeStartOffset) / SequenceModeItemWidth;
      return Math.max(10, Math.round(rawCount / 10) * 10);
    } else if (layoutMode === "snake-layout-mode") {
      var _rawCount = (position - SnakeModeStartOffset) / SnakeModeItemWidth;
      return Math.max(1, Math.round(_rawCount));
    }
    return lineLengthValue;
  }, [layoutMode, indentsInSequenceMode, lineLengthValue]);
  var calculateDragPosition = reactExports.useCallback(function(initialScreenX) {
    var dragDelta2 = initialScreenX - dragStartX.current;
    var screenX = transform.applyX(translateValue) + dragDelta2;
    return [dragDelta2, transform.invertX(screenX)];
  }, [transform, translateValue]);
  var previewValue = reactExports.useMemo(function() {
    if (!isDragging) {
      return lineLengthValue;
    }
    var _calculateDragPositio = calculateDragPosition(dragStartX.current + dragDelta), _calculateDragPositio2 = _slicedToArray(_calculateDragPositio, 2), dragPosition = _calculateDragPositio2[1];
    return calculateLineLength(dragPosition);
  }, [isDragging, lineLengthValue, calculateDragPosition, dragStartX, dragDelta, calculateLineLength]);
  var handleDragStart = reactExports.useCallback(function(event) {
    setIsDragging3(true);
    dragStartX.current = event.sourceEvent.clientX;
    editor === null || editor === void 0 || editor.events.toggleLineLengthHighlighting.dispatch(true, translateValue);
  }, [editor === null || editor === void 0 || (_editor$events2 = editor.events) === null || _editor$events2 === void 0 ? void 0 : _editor$events2.toggleLineLengthHighlighting, translateValue]);
  var handleDrag = reactExports.useCallback(function(event) {
    var _calculateDragPositio3 = calculateDragPosition(event.sourceEvent.clientX), _calculateDragPositio4 = _slicedToArray(_calculateDragPositio3, 2), dragDelta2 = _calculateDragPositio4[0], dragPosition = _calculateDragPositio4[1];
    setDragDelta(dragDelta2);
    editor === null || editor === void 0 || editor.events.toggleLineLengthHighlighting.dispatch(true, dragPosition);
  }, [editor === null || editor === void 0 || (_editor$events3 = editor.events) === null || _editor$events3 === void 0 ? void 0 : _editor$events3.toggleLineLengthHighlighting, calculateDragPosition]);
  var handleDragEnd = reactExports.useCallback(function(event) {
    setIsDragging3(false);
    var _calculateDragPositio5 = calculateDragPosition(event.sourceEvent.clientX), _calculateDragPositio6 = _slicedToArray(_calculateDragPositio5, 2), dragPosition = _calculateDragPositio6[1];
    var newValue = calculateLineLength(dragPosition);
    if (newValue !== lineLengthValue) {
      updateSettings(newValue);
    }
    setDragDelta(0);
    dragStartX.current = 0;
    editor === null || editor === void 0 || editor.events.toggleLineLengthHighlighting.dispatch(false);
  }, [calculateDragPosition, calculateLineLength, lineLengthValue, editor === null || editor === void 0 ? void 0 : editor.events.toggleLineLengthHighlighting, updateSettings]);
  if (layoutMode === "flex-layout-mode") {
    return null;
  }
  var isRulerVisible = !window._ketcher_isChainLengthRulerDisabled;
  return isRulerVisible ? jsxs("div", {
    className: clsx$2(styles$1.rulerArea, isDragging && styles$1.rulerAreaDragging),
    "data-testid": "ruler-area",
    children: [jsx(RulerInput$1, {
      lineLengthValue: isDragging ? previewValue : lineLengthValue,
      offsetX: inputOffsetX,
      isDragging,
      layoutMode,
      onCommitValue: updateSettings
    }), jsx(RulerHandle$1, {
      offsetX: handleOffsetX,
      onDragStart: handleDragStart,
      onDrag: handleDrag,
      onDragEnd: handleDragEnd
    }), jsx(RulerScale$1, {
      transform,
      layoutMode,
      lineLengthValue
    })]
  }) : null;
};
var styles = { "dragGhost": "DragGhost-module_dragGhost__m5lHf" };
var GhostRnaPreset = function GhostRnaPreset2(_ref3) {
  var _preset$phosphatePosi;
  var preset = _ref3.preset;
  var sugar = preset.sugar, phosphate = preset.phosphate, base = preset.base;
  if (!sugar) {
    return null;
  }
  var _monomerFactory = monomerFactory(sugar), _monomerFactory2 = _slicedToArray(_monomerFactory, 2), SugarMonomer = _monomerFactory2[0], SugarRenderer = _monomerFactory2[1];
  var sugarInstance = new SugarMonomer(sugar);
  var sugarRenderer = new SugarRenderer(sugarInstance);
  var phosphateRenderer = phosphate ? (function() {
    var _monomerFactory3 = monomerFactory(phosphate), _monomerFactory4 = _slicedToArray(_monomerFactory3, 2), PhosphateMonomer = _monomerFactory4[0], PhosphateRenderer = _monomerFactory4[1];
    var phosphateInstance = new PhosphateMonomer(phosphate);
    return new PhosphateRenderer(phosphateInstance);
  })() : null;
  var baseRenderer = base ? (function() {
    var _monomerFactory5 = monomerFactory(base), _monomerFactory6 = _slicedToArray(_monomerFactory5, 2), BaseMonomer2 = _monomerFactory6[0], BaseRenderer = _monomerFactory6[1];
    var baseInstance = new BaseMonomer2(base);
    return new BaseRenderer(baseInstance);
  })() : null;
  var sugarSize = sugarRenderer.monomerSize;
  var phosphateSize = phosphateRenderer === null || phosphateRenderer === void 0 ? void 0 : phosphateRenderer.monomerSize;
  var baseSize = baseRenderer === null || baseRenderer === void 0 ? void 0 : baseRenderer.monomerSize;
  var phosphatePosition = (_preset$phosphatePosi = preset.phosphatePosition) !== null && _preset$phosphatePosi !== void 0 ? _preset$phosphatePosi : getRnaPresetPhosphatePosition(preset);
  var phosphateOnLeft = phosphatePosition === "left";
  var sugarX = phosphateSize && phosphateOnLeft ? phosphateSize.width + 30 : 0;
  var sugarY = 0;
  var phosphateX = 0;
  if (phosphateSize) {
    phosphateX = phosphateOnLeft ? 0 : sugarX + sugarSize.width + 30;
  }
  var phosphateY = sugarY;
  var baseX = sugarX + (sugarSize.width - ((baseSize === null || baseSize === void 0 ? void 0 : baseSize.width) || 0)) / 2;
  var baseY = sugarY + sugarSize.height + 30;
  var totalWidth = Math.max(sugarX + sugarSize.width, phosphateSize ? phosphateX + phosphateSize.width : 0, baseSize ? baseX + baseSize.width : 0);
  var totalHeight = Math.max(sugarY + sugarSize.height, phosphateSize ? phosphateY + phosphateSize.height : 0, baseSize ? baseY + baseSize.height : 0);
  var inset = 2;
  var sugarScaleX = (sugarSize.width - inset * 2) / sugarSize.width;
  var sugarScaleY = (sugarSize.height - inset * 2) / sugarSize.height;
  var sugarScale = Math.min(sugarScaleX, sugarScaleY);
  var sugarDx = (sugarSize.width - sugarSize.width * sugarScale) / 2;
  var sugarDy = (sugarSize.height - sugarSize.height * sugarScale) / 2;
  var phosphateScale = phosphateSize ? Math.min((phosphateSize.width - inset * 2) / phosphateSize.width, (phosphateSize.height - inset * 2) / phosphateSize.height) : 1;
  var phosphateDx = phosphateSize ? (phosphateSize.width - phosphateSize.width * phosphateScale) / 2 : 0;
  var phosphateDy = phosphateSize ? (phosphateSize.height - phosphateSize.height * phosphateScale) / 2 : 0;
  var baseScale = baseSize ? Math.min((baseSize.width - inset * 2) / baseSize.width, (baseSize.height - inset * 2) / baseSize.height) : 1;
  var baseDx = baseSize ? (baseSize.width - baseSize.width * baseScale) / 2 : 0;
  var baseDy = baseSize ? (baseSize.height - baseSize.height * baseScale) / 2 : 0;
  var connectorGreyWidth = 4;
  var connectorOutlineWidth = 6;
  return jsx("svg", {
    xmlns: "http://www.w3.org/2000/svg",
    width: totalWidth,
    height: totalHeight,
    viewBox: "0 0 ".concat(totalWidth, " ").concat(totalHeight),
    overflow: "visible",
    children: jsxs("g", {
      style: {
        filter: "drop-shadow(0px 2px 2px rgba(0, 0, 0, 0.4))"
      },
      children: [jsxs("g", {
        transform: "translate(".concat(sugarX, ", ").concat(sugarY, ")"),
        children: [jsx("use", {
          href: sugarRenderer.monomerSymbolElementId,
          fill: "white"
        }), jsx("g", {
          transform: "translate(".concat(sugarDx, ", ").concat(sugarDy, ") scale(").concat(sugarScale, ")"),
          children: jsx("use", {
            href: sugarRenderer.monomerSymbolElementId,
            fill: "#CAD3DD"
          })
        }), jsx("text", {
          x: sugarSize.width / 2,
          y: sugarSize.height / 2,
          textAnchor: "middle",
          dominantBaseline: "central",
          pointerEvents: "none",
          fill: "#333",
          fontSize: "7px",
          fontWeight: "bold",
          children: sugar.label
        })]
      }), phosphateSize && jsxs("g", {
        transform: "translate(".concat(phosphateX, ", ").concat(phosphateY, ")"),
        children: [jsx("use", {
          href: phosphateRenderer.monomerSymbolElementId,
          fill: "white"
        }), jsx("g", {
          transform: "translate(".concat(phosphateDx, ", ").concat(phosphateDy, ") scale(").concat(phosphateScale, ")"),
          children: jsx("use", {
            href: phosphateRenderer.monomerSymbolElementId,
            fill: "#CAD3DD"
          })
        }), jsx("text", {
          x: phosphateSize.width / 2,
          y: phosphateSize.height / 2,
          textAnchor: "middle",
          dominantBaseline: "central",
          pointerEvents: "none",
          fill: "#333",
          fontSize: "7px",
          fontWeight: "bold",
          children: phosphate === null || phosphate === void 0 ? void 0 : phosphate.label
        })]
      }), baseSize && jsxs("g", {
        transform: "translate(".concat(baseX, ", ").concat(baseY, ")"),
        children: [jsx("use", {
          href: baseRenderer.monomerSymbolElementId,
          fill: "white"
        }), jsx("g", {
          transform: "translate(".concat(baseDx, ", ").concat(baseDy, ") scale(").concat(baseScale, ")"),
          children: jsx("use", {
            href: baseRenderer.monomerSymbolElementId,
            fill: "#CAD3DD"
          })
        }), jsx("text", {
          x: baseSize.width / 2,
          y: baseSize.height / 2,
          textAnchor: "middle",
          dominantBaseline: "central",
          pointerEvents: "none",
          fill: "#333",
          fontSize: "7px",
          fontWeight: "bold",
          children: base === null || base === void 0 ? void 0 : base.label
        })]
      }), phosphateSize && jsxs("g", {
        children: [jsx("line", {
          x1: phosphateOnLeft ? phosphateX + phosphateSize.width : sugarX + sugarSize.width,
          y1: sugarY + sugarSize.height / 2,
          x2: phosphateOnLeft ? sugarX + connectorOutlineWidth / 3 : phosphateX + connectorOutlineWidth / 3,
          y2: phosphateY + phosphateSize.height / 2,
          stroke: "white",
          strokeWidth: 7,
          strokeLinecap: "butt"
        }), jsx("line", {
          x1: phosphateOnLeft ? phosphateX + phosphateSize.width - connectorOutlineWidth / 2 : sugarX + sugarSize.width - connectorOutlineWidth / 2,
          y1: sugarY + sugarSize.height / 2,
          x2: phosphateOnLeft ? sugarX + connectorOutlineWidth / 2 : phosphateX + connectorOutlineWidth / 2,
          y2: phosphateY + phosphateSize.height / 2,
          stroke: "#CAD3DD",
          strokeWidth: connectorGreyWidth,
          strokeLinecap: "round"
        })]
      }), baseSize && jsxs("g", {
        children: [jsx("line", {
          x1: sugarX + sugarSize.width / 2,
          y1: sugarY + sugarSize.height,
          x2: baseX + baseSize.width / 2,
          y2: baseY + connectorOutlineWidth / 2,
          stroke: "white",
          strokeWidth: 7,
          strokeLinecap: "butt"
        }), jsx("line", {
          x1: sugarX + sugarSize.width / 2,
          y1: sugarY + sugarSize.height - connectorOutlineWidth / 2,
          x2: baseX + baseSize.width / 2,
          y2: baseY + connectorOutlineWidth / 2,
          stroke: "#CAD3DD",
          strokeWidth: connectorGreyWidth,
          strokeLinecap: "round"
        })]
      })]
    })
  });
};
var GhostMonomer = function GhostMonomer2(_ref3) {
  var monomerItem = _ref3.monomerItem;
  var monomerRenderer = reactExports.useMemo(function() {
    if (isAmbiguousMonomerLibraryItem(monomerItem)) {
      var monomerInstance = new AmbiguousMonomer(monomerItem);
      return new AmbiguousMonomerRenderer(monomerInstance);
    } else {
      var _monomerFactory = monomerFactory(monomerItem), _monomerFactory2 = _slicedToArray(_monomerFactory, 2), Monomer = _monomerFactory2[0], MonomerRenderer = _monomerFactory2[1];
      var _monomerInstance = new Monomer(monomerItem);
      return new MonomerRenderer(_monomerInstance);
    }
  }, [monomerItem]);
  var monomerSymbolElementId = monomerRenderer.monomerSymbolElementId;
  var monomerSize = monomerRenderer.monomerSize;
  var width = monomerSize.width, height = monomerSize.height;
  return jsxs("svg", {
    xmlns: "http://www.w3.org/2000/svg",
    width,
    height,
    viewBox: "0 0 ".concat(width, " ").concat(height),
    overflow: "visible",
    children: [jsx("use", {
      href: monomerSymbolElementId,
      fill: "#CAD3DD",
      stroke: "white",
      strokeWidth: 2,
      style: {
        filter: "drop-shadow(0px 2px 2px rgba(0, 0, 0, 0.4))"
      }
    }), jsx("text", {
      x: width / 2,
      y: height / 2,
      textAnchor: "middle",
      dominantBaseline: "central",
      pointerEvents: "none",
      fill: "#333",
      fontSize: "7px",
      fontWeight: "bold",
      children: monomerItem.label
    })]
  });
};
var DragGhost = function DragGhost2() {
  var _editor$ketcherRootEl, _editor$ketcherRootEl2;
  var editor = useSelector(selectEditor);
  var _useState = reactExports.useState(null), _useState2 = _slicedToArray(_useState, 2), libraryItemDragData = _useState2[0], setLibraryItemDragData = _useState2[1];
  var ghostWrapperRef = reactExports.useRef(null);
  var animateRef = reactExports.useRef(null);
  var canvasBBoxRef = reactExports.useRef(null);
  var transform = useZoomTransform();
  reactExports.useEffect(function() {
    if (!editor) {
      return;
    }
    var handleLibraryItemDrag = function handleLibraryItemDrag2(state) {
      setLibraryItemDragData(state);
    };
    editor.events.setLibraryItemDragState.add(handleLibraryItemDrag);
    return function() {
      editor.events.setLibraryItemDragState.remove(handleLibraryItemDrag);
    };
  }, [editor]);
  reactExports.useEffect(function() {
    if (!ZoomTool.instance || !libraryItemDragData) {
      return;
    }
    var canvasWrapper = ZoomTool.instance.canvasWrapper.node();
    if (!canvasWrapper) {
      return;
    }
    canvasBBoxRef.current = canvasWrapper.getBoundingClientRect();
  }, [libraryItemDragData]);
  var leftOffset = (editor === null || editor === void 0 || (_editor$ketcherRootEl = editor.ketcherRootElementBoundingClientRect) === null || _editor$ketcherRootEl === void 0 ? void 0 : _editor$ketcherRootEl.left) || 0;
  var topOffset = (editor === null || editor === void 0 || (_editor$ketcherRootEl2 = editor.ketcherRootElementBoundingClientRect) === null || _editor$ketcherRootEl2 === void 0 ? void 0 : _editor$ketcherRootEl2.top) || 0;
  var dragOverCanvas = canvasBBoxRef.current && libraryItemDragData && libraryItemDragData.position.x + leftOffset >= canvasBBoxRef.current.left && libraryItemDragData.position.x + leftOffset <= canvasBBoxRef.current.right && libraryItemDragData.position.y + topOffset >= canvasBBoxRef.current.top && libraryItemDragData.position.y + topOffset <= canvasBBoxRef.current.bottom;
  reactExports.useLayoutEffect(function() {
    var element = ghostWrapperRef.current;
    if (!element || !libraryItemDragData) {
      return;
    }
    animateRef.current = requestAnimationFrame(function() {
      var _libraryItemDragData$ = libraryItemDragData.position, x2 = _libraryItemDragData$.x, y2 = _libraryItemDragData$.y;
      if (dragOverCanvas && canvasBBoxRef.current) {
        var scale = transform.k;
        element.style.transformOrigin = "0 0";
        element.style.transform = "translate(".concat(x2, "px, ").concat(y2, "px) scale(").concat(scale, ")");
      } else {
        element.style.transform = "translate(".concat(x2, "px, ").concat(y2, "px)");
      }
    });
    return function() {
      if (animateRef.current) {
        cancelAnimationFrame(animateRef.current);
        animateRef.current = null;
      }
    };
  }, [dragOverCanvas, libraryItemDragData, transform.k]);
  if (!libraryItemDragData) {
    return null;
  }
  return jsx("div", {
    className: styles.dragGhost,
    ref: ghostWrapperRef,
    "data-testid": "drag-ghost",
    children: isLibraryItemRnaPreset(libraryItemDragData.item) ? jsx(GhostRnaPreset, {
      preset: libraryItemDragData.item
    }) : jsx(GhostMonomer, {
      monomerItem: libraryItemDragData.item
    })
  });
};
var _path, _path2, _path3, _path4, _defs;
function _extends() {
  return _extends = Object.assign ? Object.assign.bind() : function(n) {
    for (var e = 1; e < arguments.length; e++) {
      var t = arguments[e];
      for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]);
    }
    return n;
  }, _extends.apply(null, arguments);
}
function SvgLogo(props) {
  return /* @__PURE__ */ reactExports.createElement("svg", _extends({
    width: 22,
    height: 24,
    viewBox: "0 0 22 24",
    fill: "none",
    xmlns: "http://www.w3.org/2000/svg"
  }, props), _path || (_path = /* @__PURE__ */ reactExports.createElement("path", {
    fill: "transparent",
    d: "M0 0h21.503v24H0z"
  })), _path2 || (_path2 = /* @__PURE__ */ reactExports.createElement("path", {
    d: "M13.507 18.936l-2.04-1.92c-.7-.659-1.403-1.317-2.108-1.983v3.097c0 .43.003.86.007 1.289 0 .049-.007.09-.007.126v2.04c0 .834 0 1.557.003 2.02l.278.163c.719.3 1.434.307 2.151.033l4.264-2.469c-.358-.326-1.395-1.31-2.548-2.396zM6.159 19.39v-1.091L6.163 2.23v-.002L1.26 5.059C.421 5.647.002 6.482.002 7.553c0 2.944.006 5.888-.002 8.831-.003 1.08.398 1.913 1.212 2.517l4.946 2.856v-2.318-.05z",
    fill: "#676767"
  })), _path3 || (_path3 = /* @__PURE__ */ reactExports.createElement("path", {
    d: "M18.642 4.137l1.672.966c.785.58 1.187 1.385 1.188 2.41v8.974c0 1-.385 1.79-1.133 2.367l-1.423.822h-.004c-.097-.097-6.384-6.375-6.513-6.386.044-.044.56-.582 1.278-1.33L20.3 5.097l-1.658-.96z",
    fill: "url(#logo_svg__paint0_linear_5175_84899)"
  })), _path4 || (_path4 = /* @__PURE__ */ reactExports.createElement("path", {
    d: "M17.335 3.383L11.849.216c-.718-.29-1.455-.29-2.219.011l-.27.139s0 10.346.041 11.106c.341-.346 7.808-7.96 7.934-8.09z",
    fill: "url(#logo_svg__paint1_linear_5175_84899)"
  })), _defs || (_defs = /* @__PURE__ */ reactExports.createElement("defs", null, /* @__PURE__ */ reactExports.createElement("linearGradient", {
    id: "logo_svg__paint0_linear_5175_84899",
    x1: 19.854,
    y1: 4.363,
    x2: 11.579,
    y2: 13.111,
    gradientUnits: "userSpaceOnUse"
  }, /* @__PURE__ */ reactExports.createElement("stop", {
    stopColor: "#3BC2D7"
  }), /* @__PURE__ */ reactExports.createElement("stop", {
    offset: 0.74,
    stopColor: "#1D9DB1"
  })), /* @__PURE__ */ reactExports.createElement("linearGradient", {
    id: "logo_svg__paint1_linear_5175_84899",
    x1: 19.854,
    y1: 4.363,
    x2: 11.579,
    y2: 13.111,
    gradientUnits: "userSpaceOnUse"
  }, /* @__PURE__ */ reactExports.createElement("stop", {
    stopColor: "#3BC2D7"
  }), /* @__PURE__ */ reactExports.createElement("stop", {
    offset: 0.74,
    stopColor: "#1D9DB1"
  })))));
}
var About$1 = createStyled("div", {
  target: "e1dr48d30"
} )(function(_ref3) {
  var _theme$ketcher, _theme$ketcher2;
  var theme = _ref3.theme;
  return {
    width: "430px",
    minHeight: "260px",
    padding: "0 18px",
    borderRadius: "6px",
    fontSize: "12px",
    color: theme.ketcher.color.text.primary,
    fontWeight: (_theme$ketcher = theme.ketcher) === null || _theme$ketcher === void 0 || (_theme$ketcher = _theme$ketcher.font) === null || _theme$ketcher === void 0 || (_theme$ketcher = _theme$ketcher.weight) === null || _theme$ketcher === void 0 ? void 0 : _theme$ketcher.regular,
    a: {
      color: "#167782"
    },
    ".body": {
      borderRadius: "6px",
      padding: "5px 65px",
      overflowY: "auto",
      overflowX: "hidden",
      ".versionName": {
        fontWeight: 400,
        marginBottom: "2px"
      },
      ".firstline": {
        display: "inline-block"
      },
      ".links": {
        textAlign: "right"
      },
      ".indigoVersion": {
        marginTop: "20px",
        display: "flex",
        gap: "2px"
      }
    },
    ".headerContent": {
      display: "flex",
      justifyContent: "space-between",
      padding: "0 30px",
      a: {
        display: "flex",
        alignItems: "center",
        gap: "10px",
        textDecoration: "none",
        color: (_theme$ketcher2 = theme.ketcher) === null || _theme$ketcher2 === void 0 || (_theme$ketcher2 = _theme$ketcher2.color) === null || _theme$ketcher2 === void 0 || (_theme$ketcher2 = _theme$ketcher2.text) === null || _theme$ketcher2 === void 0 ? void 0 : _theme$ketcher2.primary
      },
      ".title": {
        fontSize: "20px",
        lineHeight: "22px"
      }
    },
    ".indigoFirstLine": {
      display: "inline-block"
    },
    dd: {
      margin: 0,
      marginBottom: "0.2em"
    },
    dt: {
      marginTop: "3px"
    },
    ".okButton": {
      border: "1px solid #333333",
      backgroundColor: "#FFFFFF",
      color: "#333333",
      display: "inline-flex",
      justifyContent: "center",
      alignItems: "center",
      outline: "none",
      minWidth: "70px",
      lineHeight: "14px",
      height: "24px",
      borderRadius: "4px",
      fontSize: "10px",
      "&:hover": {
        color: "#333333",
        border: "1px solid  #333333"
      },
      "&:active": {
        color: "#333333",
        border: "1px solid #333333"
      },
      "&:disabled": {
        color: "rgba(51, 51, 51, 0.7)",
        border: "1px solid rgba(51, 51, 51, 0.7)"
      }
    },
    ".aboutFooter": {
      borderTop: "1px solid #e1e5ea",
      margin: 0,
      padding: "15px 0",
      display: "flex",
      justifyContent: "flex-end",
      alignItems: "center"
    }
  };
}, "" );
function ownKeys$1(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$1(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$1(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$1(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
function useIndigoVersionToRedux() {
  var dispatch2 = useAppDispatch();
  var app = useAppSelector(selectAppMeta);
  reactExports.useEffect(function() {
    function fetchIndigoInfo() {
      return _fetchIndigoInfo.apply(this, arguments);
    }
    function _fetchIndigoInfo() {
      _fetchIndigoInfo = _asyncToGenerator(_regeneratorRuntime.mark(function _callee() {
        var indigo, _info$indigoVersion, info;
        return _regeneratorRuntime.wrap(function _callee$(_context) {
          while (1) switch (_context.prev = _context.next) {
            case 0:
              indigo = IndigoProvider.getIndigo();
              if (!(indigo !== null && indigo !== void 0 && indigo.info)) {
                _context.next = 11;
                break;
              }
              _context.prev = 2;
              _context.next = 5;
              return indigo.info();
            case 5:
              info = _context.sent;
              dispatch2(setAppMeta2(_objectSpread$1(_objectSpread$1({}, app), {}, {
                indigoVersion: (_info$indigoVersion = info.indigoVersion) !== null && _info$indigoVersion !== void 0 ? _info$indigoVersion : ""
              })));
              _context.next = 11;
              break;
            case 9:
              _context.prev = 9;
              _context.t0 = _context["catch"](2);
            case 11:
            case "end":
              return _context.stop();
          }
        }, _callee, null, [[2, 9]]);
      }));
      return _fetchIndigoInfo.apply(this, arguments);
    }
    fetchIndigoInfo();
  }, [dispatch2]);
}
var FEEDBACK_URL = "http://lifescience.opensource.epam.com/ketcher/#feedback";
var OVERVIEW_URL = "https://lifescience.opensource.epam.com/ketcher/index.html";
var LIFE_SCIENCES_URL = "http://lifescience.opensource.epam.com/";
var INDIGO_URL = "http://lifescience.opensource.epam.com/indigo/";
function formatDate() {
  var isoDate = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : "";
  if (!isoDate.includes("T")) return isoDate;
  var _isoDate$split = isoDate.split("T"), _isoDate$split2 = _slicedToArray(_isoDate$split, 2), date2 = _isoDate$split2[0], time = _isoDate$split2[1];
  return "".concat(date2, "; ").concat(time);
}
function About(_ref3) {
  var isOpen = _ref3.isOpen, onClose = _ref3.onClose;
  var dispatch2 = useAppDispatch();
  useIndigoVersionToRedux();
  var _useAppSelector = useAppSelector(selectAppMeta), buildDate = _useAppSelector.buildDate, indigoVersion = _useAppSelector.indigoVersion, version = _useAppSelector.version;
  var formattedDate = formatDate(buildDate);
  var handleClose = function handleClose2() {
    dispatch2({
      type: "MODAL_CLOSE"
    });
    onClose();
  };
  return jsx(Modal, {
    title: "",
    isOpen,
    onClose: handleClose,
    hideHeaderBorder: true,
    children: jsx(Modal.Content, {
      children: jsxs(About$1, {
        children: [jsx("div", {
          className: "headerContent",
          children: jsxs("a", {
            href: OVERVIEW_URL,
            target: "_blank",
            rel: "noopener noreferrer",
            children: [jsx(SvgLogo, {}), jsx("span", {
              className: "title",
              children: "Ketcher"
            })]
          })
        }), jsx("div", {
          className: "body",
          children: jsxs("dl", {
            children: [jsx("dt", {
              "data-testid": "build-version",
              children: jsxs("a", {
                href: OVERVIEW_URL,
                target: "_blank",
                rel: "noopener noreferrer",
                children: ["Version ", version]
              })
            }), jsxs("dd", {
              "data-testid": "build-time",
              children: ["Build at ", jsx("time", {
                children: formattedDate
              })]
            }), jsxs("div", {
              className: "infoLinks",
              children: [jsx("dt", {
                children: jsx("a", {
                  href: FEEDBACK_URL,
                  target: "_blank",
                  rel: "noopener noreferrer",
                  children: "Feedback"
                })
              }), jsx("dt", {
                children: jsx("a", {
                  href: LIFE_SCIENCES_URL,
                  target: "_blank",
                  rel: "noopener noreferrer",
                  children: "EPAM Life Sciences"
                })
              })]
            }), jsx("div", {
              className: "indigoVersion",
              children: jsx("a", {
                href: INDIGO_URL,
                target: "_blank",
                rel: "noopener noreferrer",
                children: "Indigo Toolkit"
              })
            }), jsx("div", {
              "data-testid": "build-indigo-version",
              children: indigoVersion ? jsxs("dd", {
                children: ["Version ", indigoVersion]
              }) : jsx("p", {
                children: "Standalone"
              })
            })]
          })
        }), jsx("div", {
          className: "aboutFooter",
          children: jsx("button", {
            onClick: handleClose,
            className: "okButton",
            "data-testid": "ok-button",
            children: "Ok"
          })
        })]
      })
    })
  });
}
function ownKeys(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
function ButtonsComponents() {
  var _useState = reactExports.useState(false), _useState2 = _slicedToArray(_useState, 2), aboutOpen = _useState2[0], setAboutOpen = _useState2[1];
  var aboutProps = {
    isOpen: aboutOpen,
    onClose: function onClose() {
      return setAboutOpen(false);
    }
  };
  return jsxs(Fragment, {
    children: [jsxs("div", {
      style: {
        display: "flex",
        alignItems: "center"
      },
      children: [jsx(IconButton, {
        iconName: "help",
        title: "Help (?)",
        onClick: function onClick() {
          var HELP_LINK = "master";
          window.open("https://github.com/epam/ketcher/blob/".concat(HELP_LINK, "/documentation/help.md#ketcher-macromolecules-mode"), "_blank");
        },
        testId: "help-button"
      }), jsx(IconButton, {
        iconName: "about",
        title: "About",
        onClick: function onClick() {
          return setAboutOpen(true);
        },
        testId: "about-button"
      })]
    }), jsx(About, _objectSpread({}, aboutProps))]
  });
}
var FloatingToolsWrapper = createStyled("div", {
  target: "e1lzguhf1"
} )("position:absolute;left:", function(props) {
  return props.left;
}, "px;top:", function(props) {
  return props.top;
}, "px;display:flex;flex-direction:row;gap:8px;transform:translate(-50%, -100%) translateY(-10px);z-index:100;" + ("" ));
var ToolButton = createStyled("button", {
  target: "e1lzguhf0"
} )({
  name: "11kiyhp",
  styles: "width:28px;height:28px;display:flex;align-items:center;justify-content:center;background:white;border:none;border-radius:4px;cursor:pointer;padding:0;color:#2b2f3a;box-shadow:0 6px 10px rgba(103, 104, 132, 0.15);&:hover{color:#188794;}&:active{background:#167782;color:#fff;}&>svg{width:20px;height:20px;}"
} );
var POSITION_EPSILON = 0.1;
var FloatingTools = function FloatingTools2() {
  var editor = useAppSelector(selectEditor);
  var _useState = reactExports.useState(false), _useState2 = _slicedToArray(_useState, 2), visible = _useState2[0], setVisible = _useState2[1];
  var _useState3 = reactExports.useState(new Vec2(0, 0)), _useState4 = _slicedToArray(_useState3, 2), position = _useState4[0], setPosition2 = _useState4[1];
  var positionRef = reactExports.useRef(new Vec2(0, 0));
  var updatePosition = reactExports.useCallback(function() {
    var _editor$drawingEntiti;
    if (!editor) return;
    var bbox = (_editor$drawingEntiti = editor.drawingEntitiesManager) === null || _editor$drawingEntiti === void 0 ? void 0 : _editor$drawingEntiti.getSelectedEntitiesBoundingBox();
    if (!bbox) return;
    var centerX = (bbox.left + bbox.right) / 2;
    var yOffset = 1.7;
    var topY = bbox.top - yOffset;
    var viewPos = Coordinates.modelToView(new Vec2(centerX, topY));
    var dx = Math.abs(viewPos.x - positionRef.current.x);
    var dy = Math.abs(viewPos.y - positionRef.current.y);
    if (dx > POSITION_EPSILON || dy > POSITION_EPSILON) {
      positionRef.current = viewPos;
      setPosition2(viewPos);
    }
  }, [editor]);
  reactExports.useEffect(function() {
    if (!editor) return;
    var handleSelectEntities = function handleSelectEntities2() {
      var _editor$drawingEntiti2, _editor$drawingEntiti3;
      var selectedEntities = (_editor$drawingEntiti2 = (_editor$drawingEntiti3 = editor.drawingEntitiesManager) === null || _editor$drawingEntiti3 === void 0 ? void 0 : _editor$drawingEntiti3.selectedEntitiesArr) !== null && _editor$drawingEntiti2 !== void 0 ? _editor$drawingEntiti2 : [];
      var selectedMonomersAndAtoms = selectedEntities.filter(function(entity) {
        return entity instanceof Atom || entity instanceof BaseMonomer;
      });
      var isTransforming = editor.selectedTool instanceof SelectBase && (editor.selectedTool.mode === "rotating" || editor.selectedTool.mode === "moving");
      var shouldShow = selectedMonomersAndAtoms.length >= 2 && editor.mode.modeName !== "sequence-layout-mode" && editor.selectedTool instanceof SelectBase && !isTransforming;
      if (shouldShow) {
        updatePosition();
        setVisible(true);
      } else {
        setVisible(false);
      }
    };
    editor.events.selectEntities.add(handleSelectEntities);
    return function() {
      editor.events.selectEntities.remove(handleSelectEntities);
    };
  }, [editor, updatePosition]);
  reactExports.useEffect(function() {
    if (!editor || !visible) return;
    var rafId = 0;
    var tick = function tick2() {
      var isTransforming = editor.selectedTool instanceof SelectBase && (editor.selectedTool.mode === "rotating" || editor.selectedTool.mode === "moving");
      if (isTransforming) {
        setVisible(false);
        return;
      }
      updatePosition();
      rafId = requestAnimationFrame(tick2);
    };
    rafId = requestAnimationFrame(tick);
    return function() {
      return cancelAnimationFrame(rafId);
    };
  }, [editor, visible, updatePosition]);
  var handleFlipHorizontal = function handleFlipHorizontal2() {
    editor === null || editor === void 0 || editor.events.flipHorizontal.dispatch();
  };
  var handleFlipVertical = function handleFlipVertical2() {
    editor === null || editor === void 0 || editor.events.flipVertical.dispatch();
  };
  var handleDelete = function handleDelete2() {
    editor === null || editor === void 0 || editor.events.deleteSelectedStructure.dispatch();
    setVisible(false);
  };
  if (!visible) {
    return null;
  }
  return jsxs(FloatingToolsWrapper, {
    left: position.x,
    top: position.y,
    children: [jsx(ToolButton, {
      onClick: handleFlipHorizontal,
      title: "Flip horizontally",
      "data-testid": "transform-flip-h",
      children: jsx(Icon, {
        name: "transform-flip-h"
      })
    }), jsx(ToolButton, {
      onClick: handleFlipVertical,
      title: "Flip vertically",
      "data-testid": "transform-flip-v",
      children: jsx(Icon, {
        name: "transform-flip-v"
      })
    }), jsx(ToolButton, {
      onClick: handleDelete,
      title: "Delete",
      "data-testid": "float-delete",
      children: jsx(Icon, {
        name: "delete"
      })
    })]
  });
};
var muiTheme = createTheme(muiOverrides);
function EditorContainer(_ref3) {
  var onInit = _ref3.onInit, ketcherId = _ref3.ketcherId, theme = _ref3.theme, togglerComponent = _ref3.togglerComponent, monomersLibraryUpdate = _ref3.monomersLibraryUpdate, monomersLibraryReplace = _ref3.monomersLibraryReplace, isMacromoleculesEditorTurnedOn = _ref3.isMacromoleculesEditorTurnedOn;
  var rootElRef = reactExports.useRef(null);
  var editorTheme = theme ? lodashExports.merge(defaultTheme, theme) : defaultTheme;
  var mergedTheme = lodashExports.merge(muiTheme, {
    ketcher: editorTheme
  });
  reactExports.useEffect(function() {
    store.dispatch(initKetcherId2(ketcherId));
  }, [ketcherId]);
  return jsx(Provider_default, {
    store,
    children: jsxs(ThemeProvider, {
      theme: mergedTheme,
      children: [jsx(Global, {
        styles: getGlobalStyles
      }), jsx(RootSizeProvider, {
        rootRef: rootElRef,
        isMacromoleculesEditorTurnedOn,
        children: jsx(EditorWrapper, {
          ref: rootElRef,
          className: EditorClassName,
          children: jsx(Editor, {
            ketcherId,
            theme: editorTheme,
            togglerComponent,
            monomersLibraryUpdate,
            monomersLibraryReplace,
            onInit
          })
        })
      })]
    })
  });
}
function Editor(_ref22) {
  var theme = _ref22.theme, togglerComponent = _ref22.togglerComponent, monomersLibraryUpdate = _ref22.monomersLibraryUpdate, monomersLibraryReplace = _ref22.monomersLibraryReplace, onInit = _ref22.onInit;
  var dispatch2 = useAppDispatch();
  var canvasRef = reactExports.useRef(null);
  var errorTooltips = useAppSelector(selectErrorTooltips);
  var editor = useAppSelector(selectEditor);
  var isHandToolSelected = useAppSelector(selectIsHandToolSelected);
  var isLoading = useLoading();
  var _useState = reactExports.useState(false), _useState2 = _slicedToArray(_useState, 2), isMonomerLibraryHidden = _useState2[0], setIsMonomerLibraryHidden = _useState2[1];
  var isSequenceEditInRNABuilderMode = useSequenceEditInRNABuilderMode();
  var _useState3 = reactExports.useState(), _useState4 = _slicedToArray(_useState3, 2), selections = _useState4[0], setSelections = _useState4[1];
  var _useState5 = reactExports.useState(), _useState6 = _slicedToArray(_useState5, 2), contextMenuEvent = _useState6[0], setContextMenuEvent = _useState6[1];
  var _useState7 = reactExports.useState([]), _useState8 = _slicedToArray(_useState7, 2), selectedMonomers = _useState8[0], setSelectedMonomers = _useState8[1];
  var _useContextMenu = Fe({
    id: CONTEXT_MENU_ID.FOR_SEQUENCE
  }), showSequenceContextMenu = _useContextMenu.show;
  var _useContextMenu2 = Fe({
    id: CONTEXT_MENU_ID.FOR_SELECTED_MONOMERS
  }), showSelectedMonomersContextMenu = _useContextMenu2.show;
  reactExports.useEffect(function() {
    dispatch2(createEditor2({
      theme,
      canvas: canvasRef.current,
      monomersLibraryUpdate,
      monomersLibraryReplace,
      onInit
    }));
    return function() {
      dispatch2(destroyEditor2(null));
    };
  }, [dispatch2]);
  useSetRnaPresets();
  useMacromoleculesHotkeys();
  reactExports.useEffect(function() {
    editor === null || editor === void 0 || editor.events.rightClickSequence.add(function(_ref3) {
      var _ref4 = _slicedToArray(_ref3, 2), event = _ref4[0], selections2 = _ref4[1];
      setSelections(selections2);
      setContextMenuEvent(event);
      window.dispatchEvent(new Event("hidePreview"));
      dispatch2(setContextMenuActive2(true));
      showSequenceContextMenu({
        event,
        props: {
          sequenceItemRenderer: event.target.__data__
        }
      });
    });
    editor === null || editor === void 0 || editor.events.rightClickPolymerBond.add(function(_ref5) {
      var _ref6 = _slicedToArray(_ref5, 2), event = _ref6[0], polymerBondRenderer = _ref6[1];
      setContextMenuEvent(event);
      setSelectedMonomers([]);
      showSelectedMonomersContextMenu({
        event,
        props: {
          polymerBondRenderer
        }
      });
    });
    editor === null || editor === void 0 || editor.events.rightClickSelectedMonomers.add(function(_ref7) {
      var _ref8 = _slicedToArray(_ref7, 2), event = _ref8[0], selectedMonomers2 = _ref8[1];
      setSelectedMonomers(selectedMonomers2);
      setContextMenuEvent(event);
      showSelectedMonomersContextMenu({
        event,
        props: {
          selectedMonomers: selectedMonomers2
        }
      });
    });
    editor === null || editor === void 0 || editor.events.rightClickCanvas.add(function(_ref9) {
      var _ref0 = _slicedToArray(_ref9, 2), event = _ref0[0], selections2 = _ref0[1];
      setContextMenuEvent(event);
      window.dispatchEvent(new Event("hidePreview"));
      dispatch2(setContextMenuActive2(true));
      setSelectedMonomers(selections2);
      showSelectedMonomersContextMenu({
        event,
        props: {
          selectedMonomers: selections2
        }
      });
    });
    editor === null || editor === void 0 || editor.events.rightClickCanvasSequence.add(function(_ref1) {
      var _ref10 = _slicedToArray(_ref1, 2), event = _ref10[0], selections2 = _ref10[1];
      setContextMenuEvent(event);
      window.dispatchEvent(new Event("hidePreview"));
      dispatch2(setContextMenuActive2(true));
      setSelections(selections2);
      showSequenceContextMenu({
        event,
        props: {}
      });
    });
    editor === null || editor === void 0 || editor.events.toggleMacromoleculesPropertiesVisibility.add(function() {
      dispatch2(toggleMacromoleculesPropertiesWindowVisibility2({}));
    });
  }, [editor]);
  reactExports.useEffect(function() {
    editor === null || editor === void 0 || editor.zoomTool.observeCanvasResize();
    return function() {
      editor === null || editor === void 0 || editor.zoomTool.destroy();
    };
  }, [editor]);
  reactExports.useEffect(function() {
    var setEditorLineLengthListener = function setEditorLineLengthListener2(event) {
      var lineLengthUpdate = event.detail;
      if (lineLengthUpdate) {
        dispatch2(setEditorLineLength2(lineLengthUpdate));
      }
    };
    window.addEventListener(SetEditorLineLengthAction, setEditorLineLengthListener);
    return function() {
      window.removeEventListener(SetEditorLineLengthAction, setEditorLineLengthListener);
    };
  }, [dispatch2]);
  var handleCloseErrorTooltip = function handleCloseErrorTooltip2(text) {
    dispatch2(closeErrorTooltip2(text));
  };
  var toggleLibraryVisibility = reactExports.useCallback(function() {
    setIsMonomerLibraryHidden(function(prev) {
      return !prev;
    });
  }, []);
  return jsxs(Fragment, {
    children: [jsxs(Layout, {
      children: [jsxs(Layout.Top, {
        shortened: !isMonomerLibraryHidden,
        "data-testid": "top-toolbar",
        children: [jsx(TopMenuComponent, {}), jsxs(TopMenuRightWrapper, {
          children: [jsx(SequenceSyncEditModeButton, {}), jsx(LayoutModeButton, {}), jsx(SequenceTypeGroupButton, {}), jsx(TogglerComponentWrapper, {
            className: isSequenceEditInRNABuilderMode ? "toggler-component-wrapper--disabled" : "",
            children: togglerComponent
          }), jsx(VerticalDivider, {}), jsx(ButtonsComponents, {}), jsx(FullscreenButton, {}), jsx(VerticalDivider, {}), jsx(ZoomControls, {})]
        })]
      }), jsx(Layout.Left, {
        children: jsx(LeftMenuComponent, {})
      }), jsxs(Layout.Main, {
        children: [jsx(EditorEvents, {}), jsx(RulerArea, {}), jsxs(CanvasWrapper, {
          id: "polymer-editor-canvas",
          "data-testid": "ketcher-canvas",
          "data-canvasmode": "macromolecules-mode",
          preserveAspectRatio: "xMidYMid meet",
          ref: canvasRef,
          width: "100%",
          height: "100%",
          style: {
            overflow: "hidden",
            overflowClipMargin: "content-box"
          },
          children: [jsxs("defs", {
            children: [jsx(PeptideAvatar, {}), jsx(ChemAvatar, {}), jsx(SugarAvatar, {}), jsx(PhosphateAvatar, {}), jsx(RNABaseAvatar, {}), jsx(UnresolvedMonomerAvatar, {}), jsx(NucleotideAvatar, {}), jsx(SequenceStartArrow, {}), jsx(ArrowMarker, {})]
          }), jsx("g", {
            className: "drawn-structures",
            "data-testid": "drawn-structures"
          }), isHandToolSelected && jsx("rect", {
            x: 0,
            y: 0,
            width: "100%",
            height: "100%",
            fill: "transparent",
            pointerEvents: "all"
          })]
        }), jsx(FloatingTools, {}), isLoading && jsx(Loader, {})]
      }), jsx(Layout.Right, {
        hide: isMonomerLibraryHidden,
        children: jsx(MonomerLibrary, {
          toggleLibraryVisibility
        })
      }), jsx(Layout.Bottom, {
        children: jsx(MacromoleculePropertiesWindow, {})
      }), jsx(Layout.InsideRoot, {
        children: isMonomerLibraryHidden && jsx(MonomerLibraryToggle, {
          onClick: toggleLibraryVisibility
        })
      })]
    }), jsx(Preview, {}), jsx(DragGhost, {}), jsx(SequenceItemContextMenu, {
      selections,
      contextMenuEvent
    }), jsx(SelectedMonomersContextMenu, {
      selectedMonomers,
      contextMenuEvent
    }), jsx(ModalContainer, {}), jsx(ErrorModal, {}), jsx(Snackbar, {
      anchorOrigin: {
        vertical: "bottom",
        horizontal: "center"
      },
      open: errorTooltips.length > 0,
      onClose: function onClose() {
        return handleCloseErrorTooltip();
      },
      autoHideDuration: 6e3,
      children: jsx(StyledToastContainer, {
        id: "error-tooltip",
        children: errorTooltips.map(function(text) {
          return jsxs(StyledToast, {
            children: [jsx(StyledToastContent, {
              "data-testid": "error-tooltip",
              children: text
            }), jsx(StyledIconButton$1, {
              testId: "error-tooltip-close",
              iconName: "close",
              onClick: function onClick() {
                return handleCloseErrorTooltip(text);
              }
            })]
          }, text);
        })
      })
    })]
  });
}

export { EditorContainer as default };
