const alternatives={
 'CFTC Press':'https://www.cftc.gov/PressRoom/PressReleases',
 'CFTC Speeches':'https://www.cftc.gov/PressRoom/SpeechesTestimony/index.htm'
};
const escape=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
export function cftcRss(html){
 const items=[];
 for(const m of html.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)){
  const date=m[1].match(/<time\b[^>]*datetime="([^"]+)"/i)?.[1];
  const a=m[1].match(/<a\b[^>]*href="(\/PressRoom\/(?:PressReleases|SpeechesTestimony)\/[^"]+)"[^>]*>([\s\S]*?)<\/a>/i);
  if(!date||!a||!Number.isFinite(Date.parse(date)))continue;
  items.push('<item><title>'+escape(a[2].replace(/<[^>]+>/g,'').trim())+'</title><link>'+escape('https://www.cftc.gov'+a[1])+'</link><pubDate>'+new Date(date).toUTCString()+'</pubDate></item>');
 }
 if(!items.length)throw Error('공식 목록에서 날짜/제목을 확인하지 못했습니다');
 return '<rss><channel>'+items.join('')+'</channel></rss>';
}
export async function fetchNews(name,url,{fetcher=fetch,signal}={}){
 async function read(u){const r=await fetcher(u,{headers:{'User-Agent':'CoinIssueAI-Cloud/1.0','Accept':'application/rss+xml, application/atom+xml, text/xml, text/html'},signal});if(!r.ok)throw Error('HTTP '+r.status);return await r.text();}
 try{const xml=await read(url);if(!/<(?:rss|feed)\b/i.test(xml))throw Error('RSS 대신 HTML/알 수 없는 문서 반환');return {xml,source_url:url};}
 catch(e){if(!alternatives[name])throw e;try{return {xml:cftcRss(await read(alternatives[name])),source_url:alternatives[name],fallback:true};}catch(f){throw Error('RSS '+e.message+' / 공식 목록 '+f.message);}}
}
