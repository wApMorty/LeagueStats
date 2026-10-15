// Polices libres du client (OFL), chargées avant le premier rendu.
import { continueRender, delayRender } from "remotion";
import cormorant from "../../../../src/client/static/fonts/cormorant-garamond-600.woff2";
import cormorantItalic from "../../../../src/client/static/fonts/cormorant-garamond-500-italic.woff2";
import alegreya400 from "../../../../src/client/static/fonts/alegreya-sans-400.woff2";
import alegreya500 from "../../../../src/client/static/fonts/alegreya-sans-500.woff2";
import alegreya700 from "../../../../src/client/static/fonts/alegreya-sans-700.woff2";
import runic from "../../../../src/client/static/fonts/noto-sans-runic.woff2";

const faces: [string, string, FontFaceDescriptors][] = [
  ["Cormorant Garamond", cormorant, { weight: "600" }],
  ["Cormorant Garamond", cormorantItalic, { weight: "500", style: "italic" }],
  ["Alegreya Sans", alegreya400, { weight: "400" }],
  ["Alegreya Sans", alegreya500, { weight: "500" }],
  ["Alegreya Sans", alegreya700, { weight: "700" }],
  ["Noto Sans Runic", runic, { weight: "400" }],
];

const handle = delayRender("polices du client");
Promise.all(
  faces.map(([family, url, descriptors]) =>
    new FontFace(family, `url(${url})`, descriptors).load().then((face) => document.fonts.add(face)),
  ),
).then(() => continueRender(handle));
