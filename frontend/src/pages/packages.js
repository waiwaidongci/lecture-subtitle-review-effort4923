import {feedback, field} from '../components/common/fields.js';
import {empty, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';
import {date} from '../utils/format.js';

const SOURCE = {csv:'CSV 整包实耗', correction:'更正记录', conflict:'冲突待更正'};

function correctionForm(datasetId, spec, refresh) {
  const message = feedback();
  const submit = button('提交整包更正', {class:'primary', type:'submit', 'data-testid':'correction-submit'});
  return el('form', {class:'fields', onSubmit:handler(submit, message, async event => {
    const data = new FormData(event.target);
    await workspace.correct(datasetId, {
      package_id:data.get('package_id'),
      actual_minutes:Number(data.get('actual_minutes')),
      reason:data.get('reason'),
    });
    await refresh();
  })},
    field({key:'package_id', label:'整包包号', type:'string', max_length:60}),
    field({key:'actual_minutes', label:'更正后整包实耗（分钟）', type:'number', min:0.01, max:10080}),
    el('label', {class:'field', for:'correction-reason'}, el('span', {}, '更正依据'),
      el('textarea', {id:'correction-reason', name:'reason', required:true, maxlength:500, rows:3})),
    p('更正采用追加记录：并发提交的两笔都会保留，计算默认取时间最新的一笔。', 'subtle'),
    submit, message);
}

export async function packagesPage(route, refresh) {
  const {spec, datasets} = workspace;
  const selected = datasets.find(item => item.id === route.id) || datasets[0];
  if (!selected) return panel(spec.pages[2], empty('没有可用的批次。请先在「讲座工单」导入 CSV。', '#inputs', '前往导入'));
  const detail = await workspace.packages(selected.id);

  const picker = el('label', {class:'field', for:'package-dataset'}, el('span', {}, '选择数据批次'),
    el('select', {id:'package-dataset', onChange:event => { location.hash = `#packages/${event.target.value}`; }},
      datasets.map(item => el('option', {value:item.id, selected:item.id === selected.id}, item.name))));

  const groupRows = detail.groups.map(group => ({
    package_id: group.package_ids.join('、'),
    job_id: group.job_ids.join('、'),
    job_date: group.job_date,
    last_date: group.last_date,
    title: group.titles.join('；'),
    actual_minutes: group.actual_minutes ?? '—',
    source: SOURCE[group.source] || group.source,
  }));
  const groups = panel('整包归组与实耗',
    p('共享工单号的包已自动并为一组；整包实耗只记在包上，不向单笔工单摊填。', 'subtle'),
    detail.conflict_notes?.length && el('div', {class:'decision', role:'alert'},
      detail.conflict_notes.map(note => p(note, 'feedback'))),
    table([
      {key:'package_id', label:'整包包号'}, {key:'job_id', label:'组内工单号'},
      {key:'job_date', label:'最早工单日期'}, {key:'last_date', label:'最晚工单日期'},
      {key:'title', label:'讲座标题'}, {key:'actual_minutes', label:'整包实耗（分钟）'},
      {key:'source', label:'实耗来源'},
    ], groupRows, {caption:'整包归组与实耗', empty:'该批次没有整包工单。'}));

  const history = panel('更正记录（追加保留）',
    p('每次更正都独立留痕；同一包有多笔时，最新一笔参与重新归组后的计算。', 'subtle'),
    table([
      {key:'id', label:'#'}, {key:'package_id', label:'整包包号'},
      {key:'actual_minutes', label:'整包实耗（分钟）'}, {key:'reason', label:'更正依据'},
      {key:'author', label:'操作者'}, {label:'时间', render:row => date(row.created_at)},
    ], detail.corrections, {caption:'更正记录', empty:'还没有更正记录。'}));

  const sidebar = el('aside', {class:'sidebar-panel'},
    panel('批次选择', picker, link('查看批次明细', `#inputs/${selected.id}`, {class:'quiet'})),
    session.canWrite && panel('提交更正', correctionForm(selected.id, spec, refresh)),
    panel('归组口径', el('ul', {class:'method-list'}, [
      '填写同一个包号的工单合为一条组观测，特征按成员求和、目标为整包实耗。',
      '共享工单号的包传递合并；成员日期跨越切分界的组不纳入回测。',
      '源数据重新导入或新增更正后，旧运行按数据指纹标记失效，重算时重新归组。',
    ].map(text => el('li', {}, text)))));

  return el('div', {class:'two-col'}, el('div', {class:'wide-panel'}, groups, history), sidebar);
}
