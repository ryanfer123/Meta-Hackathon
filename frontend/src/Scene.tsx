import type { Frame } from './types';
const colors: Record<string, string> = { tube_1: '#64b5f6', tube_2: '#ee7777', tube_3: '#f0d367', tube_4: '#74c99a', cap_1: '#64b5f6', label_1: '#e4e8dc', dropper: '#c6d3dc', hand: '#b8a291', holder: '#7f9690' };
export function Scene({ frame, masks }: { frame: Frame; masks: boolean }) {
  return <svg className="scene" viewBox="0 0 640 360" role="img" aria-label="Simulated top-down tabletop scene, with object positions from synthetic masks">
    <defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#526057" strokeWidth=".4" opacity=".3"/></pattern><linearGradient id="bench" x2="1" y2="1"><stop stopColor="#2b3430"/><stop offset="1" stopColor="#202824"/></linearGradient></defs>
    <rect x="8" y="8" width="624" height="344" rx="13" fill="url(#bench)" stroke="#586359"/>
    <rect x="8" y="8" width="624" height="344" rx="13" fill="url(#grid)"/>
    <text x="29" y="33" fill="#8c9c90" fontSize="9" letterSpacing="2">COLORED-WATER HANDLING / TOP VIEW</text>
    <rect x="104" y="147" width="320" height="131" rx="10" fill="#111a16" opacity=".5"/>
    <rect x="101" y="145" width="320" height="126" rx="9" fill="#677269" stroke="#89948b" strokeWidth="2"/>
    <rect x="109" y="153" width="304" height="108" rx="6" fill="#36443b"/>
    {[147, 227, 307, 387].map(x => <g key={x}><ellipse cx={x} cy="250" rx="24" ry="8" fill="#17231c"/><ellipse cx={x} cy="180" rx="24" ry="8" fill="#17231c"/></g>)}
    <text x="120" y="291" fontSize="9" fill="#9daca2" letterSpacing="2">TUBE RACK</text>
    <rect x="415" y="60" width="61" height="44" rx="6" fill="#1b241f" stroke="#68746b"/>
    <text x="422" y="54" fontSize="9" fill="#b1bdb3">CAPS</text>
    <rect x="242" y="290" width="74" height="52" rx="3" fill="#49574d" stroke="#758276"/>
    {[0, 1, 2].map(i => <rect key={i} x={248+i*20} y="300" width="15" height="30" rx="2" fill="#c0c9be" opacity=".45"/>)}
    <text x="240" y="282" fontSize="9" fill="#b1bdb3">LABELS</text>
    {Object.entries(frame.objects).filter(([, d]) => d !== null).map(([name, d]) => {
      if (!d) return null; const c = colors[name] ?? '#ced7c8';
      return <g key={name}>
        {name.startsWith('tube') ? <g><rect x={d.x} y={d.y} width={d.w} height={d.h} rx="13" fill={c} fillOpacity=".19" stroke={c} strokeWidth="1.5"/><rect x={d.x+4} y={d.y+47} width={d.w-8} height={d.h-53} rx="9" fill={c} opacity=".48"/><ellipse cx={d.x+d.w/2} cy={d.y+3} rx={d.w/2} ry="5" fill="#a6b6a9" opacity=".6"/>{[25,35,45,55,65].map(y=><line key={y} x1={d.x+5} x2={d.x+11} y1={d.y+y} y2={d.y+y} stroke="#c6d4ca" opacity=".5"/>)}</g>
        : name === 'hand' ? <g opacity=".68"><rect x={d.x} y={d.y} width={d.w} height={d.h} rx="12" fill={c}/><path d={`M${d.x+8} ${d.y+5}v${d.h-10}m8 -${d.h-10}v${d.h-10}m8 -${d.h-10}v${d.h-10}`} stroke="#62584b" strokeWidth="1"/></g>
        : name === 'dropper' ? <g><rect x={d.x-3} y={d.y} width={d.w+6} height="24" rx="7" fill="#8fa3a6"/><rect x={d.x+3} y={d.y+19} width={d.w-6} height={d.h-19} rx="3" fill="#bdcdd0" stroke="#d3dfe0"/></g>
        : <rect x={d.x} y={d.y} width={d.w} height={d.h} rx={name === 'holder' ? 5 : 3} fill={c} fillOpacity={name === 'holder' ? .12 : .9} stroke={c}/>}
        {masks && name !== 'hand' && <g><rect x={d.x-4} y={d.y-4} width={d.w+8} height={d.h+8} rx="4" fill="none" stroke={c} strokeWidth=".8" strokeDasharray={name === 'holder' ? '4 3' : undefined}/><rect x={d.x-4} y={d.y-21} width={Math.max(43,name.length*5.1+9)} height="14" rx="2" fill="#16221c" stroke={c} strokeWidth=".65"/><text x={d.x} y={d.y-11} fontSize="8" fill={c}>{name.replace('_',' ')}</text></g>}
      </g>;
    })}
    <text x="29" y="333" fontSize="8" fill="#a9b6ab" letterSpacing="1">SYNTHETIC MASKS · NO CAMERA FOOTAGE</text>
    <path d="M595 312h16v16m-16-16v16h16" fill="none" stroke="#a4b59f" strokeWidth="1"/>
  </svg>;
}
