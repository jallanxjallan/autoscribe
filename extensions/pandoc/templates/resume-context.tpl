% ---------- Page + fonts ----------
\setuppapersize[A4][A4]
\setuplayout[margin=14mm, topspace=12mm, backspace=16mm, header=0pt, footer=0pt]
\setupbodyfont[modern,11pt] % try: termes, pagella, latinmodern

% ---------- Colors ----------
\definecolor[accent][x=0.20,y=0.55,z=0.75]
\definecolor[textgray][s=0.15]

% ---------- Headings ----------
\setuphead[section][style=\ss\bfd, color=accent, before={\blank[medium]}, after={\blank[small]}]
\setuphead[subsection][style=\ss\bf, color=black, before={\blank[small]}, after={\blank[small]}]

% ---------- Lists ----------
\setupitemize[packed,autointro]

% ---------- Tables (used for the two-column block) ----------
\setuptables
  [frame=off,
   option={stretch},
   style=\strut,
   bodyfont=,
   distance=1.5ex]

% Make the first table (Profile/Skills) look like columns
\setupTABLE[frame=off]
\setupTABLE[row][1][topframe=off,bottomframe=off]
\setupTABLE[column][1][width=.48\textwidth,align=left]
\setupTABLE[column][2][width=.48\textwidth,align=left]

% ---------- Small helpers ----------
\def\SoftRule{\noindent{\color[accent]{\ruledhskip 1pt plus 1fill}}\par}

% ---------- Project entry macro (used by Pandoc’s normal text) ----------
\def\Project#1#2#3{%
  \bfb #1\par
  {\it #2}\par
  \blank[small]
  #3\par
  \blank[small]
}

% ---------- Body ----------
\starttext
$body$
\stoptext
 
