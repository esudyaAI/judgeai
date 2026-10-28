import { fileExt, mapAnalysis, type Message } from '../api/client';
import { FileChip } from '../components/FileTile';
import { fileReadingLabel } from './fileReadingPresentation';
import { Result, Thinking } from './screens';

const STAGES = ['reading', 'searching', 'qualifying', 'checking'];
const LABELS = ['Читаем документы', 'Ищем похожие дела', 'Извлекаем факты', 'Проверяем нормы закона'];
export type ChatAttachment = Message['attachments'][number];

export function ChatTimeline({messages, onOpen}: {messages: Message[]; onOpen: (attachment: ChatAttachment) => void}) {
  return <div className="thread chat-timeline" aria-label="История переписки">
    {messages.map(message => {
      const busy = message.status === 'pending' || message.status === 'running';
      const stage = STAGES.indexOf(message.stage || 'reading');
      return <section key={message.id} data-message-id={message.id} className={`chat-message chat-message-${message.role}`} aria-label={message.role === 'user' ? 'Ваше сообщение' : 'Ответ помощника'}>
        {message.role === 'user' ? <div className="thread-user"><div className="bubble">
          {message.content && <p className="chat-message-text">{message.content}</p>}
          <div className="chips">{message.attachments.map(a => <div key={a.id}>
            <button type="button" className="document-chip" aria-label={`Открыть ${a.filename}`} onClick={() => onOpen(a)}><FileChip name={a.filename} ext={fileExt(a.filename)} /></button>
            <div className="file-meta">{fileReadingLabel({pages:a.page_count || 0, recognition:a.extraction_status})}</div>
          </div>)}</div>
        </div></div> : busy ? <div aria-busy="true"><Thinking steps={LABELS.map((label,i) => ({label,done:stage > i,active:stage === i}))} /></div> : message.status === 'failed' ?
          <div className="warn-box" role="alert">{message.error || 'Анализ не выполнен. Отправьте уточнение, чтобы повторить попытку.'}</div> :
          message.result ? <Result a={mapAnalysis(message.result)} /> : <div className="thread-ai chat-message-text">{message.content}</div>}
      </section>;
    })}
  </div>;
}
