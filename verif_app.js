// Contrôle statique de index.html.
//
// Trois fois de suite, une modification a supprimé des fonctions encore
// appelées ailleurs dans le fichier : le navigateur ne le signale qu'au
// moment où le code s'exécute, et une page à moitié morte ressemble à une
// page vide. Ce script exécute le script dans un bac à sable muni d'un faux
// DOM, appelle chaque fonction de rendu sur des données réalistes, et
// échoue bruyamment si un identifiant manque.
//
//     node verif_app.js
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync(__dirname + '/app.html', 'utf8');
const js = html.match(/<script>([\s\S]*)<\/script>/)[1];

const noeud = () => new Proxy({
  style:{}, dataset:{}, classList:{add(){},remove(){}},
  setAttribute(){}, appendChild(){}, querySelector:()=>noeud(),
  querySelectorAll:()=>[], addEventListener(){}, innerHTML:'', textContent:'', value:'200000',
}, { get:(c,p)=> p in c ? c[p] : (()=>noeud()), set:(c,p,v)=>(c[p]=v,true) });

const bac = {
  document:{ getElementById:()=>noeud(), createElement:()=>noeud(),
             addEventListener(){}, querySelectorAll:()=>[] },
  fetch:()=>Promise.reject(new Error('hors ligne')),
  console, Math, Date, JSON, Intl, setTimeout,
};
bac.window = bac;
vm.createContext(bac);
vm.runInContext(js, bac, {filename:'app.html'});

// Un titre complet : tous les blocs doivent savoir le rendre.
const titre = {
  t:'SNTS', n:'Sonatel', p:'Sénégal', s:'Télécommunications', c:38800, d:'2026-09-11',
  l:'liquide', v:196197200, o:19619720, h:38800, b:24400, va:57.1, r:1.0,
  h5:38800, b5:13500, vol:16.3, dd:-1.5, w0:'2021-09-20',
  w:Array.from({length:260},(_,i)=>13500+Math.round(i*95)),
  div:{n:10,consec:9,dix:10,baisses:1,montant:1500,exercice:2025,rdt:4.5,ex:'2026-07-01',
       hist:[[2016,900],[2017,950],[2018,1000],[2020,800],[2021,1100],[2022,1200],
             [2023,1300],[2024,1400],[2025,1500]]},
  val:{per:9.86,bpa:3934,payout:38.1,niveau:'confortable',comptes:'2025-07-08',vieux:true},
  fin:{ok:true,publie_le:'2026-02-16',url:'https://x/y.pdf',rn:393400000000,rn_conf:'elevee',
       cp:900000000000,ca:1923100000000,marge:20.5,roe:43.7,payout:38.1,exercice:2025,
       serie:{exercices:5,suffisant:true,de:2021,a:2025,croissance_ca_pct:9.5,
         croissance_resultat_pct:12.5,croissance_capitaux_propres_pct:8.8,
         marges:{2021:8,2022:8.4,2023:7.1,2024:8.3,2025:8.9},marge_derniere:8.9,
         marge_tendance:0.9,roes:{2021:13.3,2022:14.4,2023:12.4,2024:14.5,2025:15.2},
         roe_dernier:15.2,exercices_deficitaires:0,exercices_en_recul:1,
         conversion_tresorerie_pct:122,dette_sur_fonds_propres_pct:29}},
  sect:{per:8.4,payout:55,roe:14.2,marge:9.1},
  ann:[{d:'2026-08-17',t:'rapport_activite',i:true,x:"Rapport d'activités",u:'https://x/z.pdf'}],
};
// Un titre dépouillé : aucun bloc ne doit planter sur des champs absents.
const nu = {t:'XXXX', n:'Inconnu', p:'Mali', s:'Industrie', c:1000, d:'2026-09-11',
            l:'inconnue', w:[1000,1010], div:null, val:null, fin:null, ann:null};

// Les déclarations `const` vivent dans la portée lexicale du contexte et
// n'apparaissent pas comme propriétés du bac à sable : on les récupère en
// évaluant leur nom dans ce même contexte.
const prendre = (nom) => {
  try { return vm.runInContext(nom, bac); } catch (e) { return undefined; }
};
const aTester = ['courbe','courbeDiv','blocCriteres','blocDiv','blocVal','blocFin','blocAnn',
                 'lecture','scoreDe','fmt','pc','joliPas','CRITERES','blocCroissance','croissanceDiv','blocFonda','resume'];
let echecs = 0;
const F = {};
for (const nom of aTester) {
  const v = prendre(nom);
  if (v === undefined) { console.log(`  ABSENTE : ${nom}`); echecs++; }
  else F[nom] = v;
}
const essai = (etiquette, fn) => {
  try { fn(); } catch (e) { console.log(`  ÉCHEC ${etiquette} : ${e.message}`); echecs++; }
};
for (const [nom, x] of [['titre complet', titre], ['titre sans données', nu]]) {
  essai(`blocCriteres/${nom}`, ()=>F.blocCriteres(x, 200000));
  essai(`blocDiv/${nom}`,      ()=>F.blocDiv(x));
  essai(`blocCroissance/${nom}`, ()=>F.blocCroissance(x));
  essai(`blocFonda/${nom}`,    ()=>F.blocFonda(x));
  essai(`resume/${nom}`,       ()=>F.resume(x, 200000));
  essai(`blocVal/${nom}`,      ()=>F.blocVal(x));
  essai(`blocFin/${nom}`,      ()=>F.blocFin(x));
  essai(`blocAnn/${nom}`,      ()=>F.blocAnn(x));
  essai(`lecture/${nom}`,      ()=>F.lecture(x, 200000));
  essai(`courbe/${nom}`,       ()=>F.courbe(x.w, x.h||1, x.b||1, x.w0, x.d));
  if (x.div) essai(`courbeDiv/${nom}`, ()=>F.courbeDiv(x.div.hist));
}
console.log(echecs ? `${echecs} problème(s)` : 'Aucun problème : tous les blocs rendent.');
process.exit(echecs ? 1 : 0);
