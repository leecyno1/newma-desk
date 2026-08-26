package menu

import (
	"fmt"
	"sort"

	"github.com/sjzar/chatlog/internal/ui/style"

	"github.com/gdamore/tcell/v2"
	"github.com/rivo/tview"
)

type Item struct {
	Index       int
	Key         string
	Name        string
	Description string
	Hidden      bool
	Selected    func(i *Item)
}

type Menu struct {
	*tview.Box
	title string
	table *tview.Table
	items []*Item
}

func New(title string) *Menu {
	menu := &Menu{
		Box:   tview.NewBox(),
		title: title,
		items: make([]*Item, 0),
		table: tview.NewTable(),
	}

	menu.table.SetBorders(false)
	menu.table.SetSelectable(true, false)
	menu.table.SetTitle(fmt.Sprintf("[::b]%s", menu.title))
	menu.table.SetBorderColor(style.BorderColor)
	menu.table.SetBackgroundColor(style.BgColor)
	menu.table.SetTitleColor(style.FgColor)
	menu.table.SetFixed(1, 0)
	menu.table.Select(1, 0).SetSelectedFunc(func(row, column int) {
		if row == 0 {
			return // 忽略表头
		}

		item, ok := menu.table.GetCell(row, 0).GetReference().(*Item)
		if ok {
			if item.Selected != nil {
				item.Selected(item)
			}
		}
	})

	menu.setTableHeader()

	return menu
}

func (m *Menu) setTableHeader() {
	m.table.SetCell(0, 0, tview.NewTableCell(fmt.Sprintf("[black::b]%s", "命令")).
		SetExpansion(1).
		SetBackgroundColor(style.PageHeaderBgColor).
		SetTextColor(style.PageHeaderFgColor).
		SetAlign(tview.AlignLeft).
		SetSelectable(false))

	m.table.SetCell(0, 1, tview.NewTableCell(fmt.Sprintf("[black::b]%s", "说明")).
		SetExpansion(2).
		SetBackgroundColor(style.PageHeaderBgColor).
		SetTextColor(style.PageHeaderFgColor).
		SetAlign(tview.AlignLeft).
		SetSelectable(false))
}

func (m *Menu) AddItem(item *Item) {
	m.items = append(m.items, item)
	sort.Sort(SortItems(m.items))
	m.refresh()
}

func (m *Menu) SetItems(items []*Item) {
	m.items = items
	m.refresh()
}

func (m *Menu) GetItems() []*Item {
	return m.items
}

func (m *Menu) refresh() {
	m.table.Clear()
	m.setTableHeader()

	row := 1
	for _, item := range m.items {
		if item.Hidden {
			continue
		}
		m.table.SetCell(row, 0, tview.NewTableCell(item.Name).
			SetTextColor(style.FgColor).
			SetBackgroundColor(style.BgColor).
			SetReference(item).
			SetAlign(tview.AlignLeft))
		m.table.SetCell(row, 1, tview.NewTableCell(item.Description).
			SetTextColor(style.FgColor).
			SetBackgroundColor(style.BgColor).
			SetReference(item).
			SetAlign(tview.AlignLeft))
		row++
	}

}

func (m *Menu) Draw(screen tcell.Screen) {
	m.refresh()

	m.Box.DrawForSubclass(screen, m)
	m.Box.SetBorder(false)

	menuViewX, menuViewY, menuViewW, menuViewH := m.GetInnerRect()

	m.table.SetRect(menuViewX, menuViewY, menuViewW, menuViewH)
	m.table.SetBorder(true).SetBorderColor(style.BorderColor)

	m.table.Draw(screen)
}

func (m *Menu) Focus(delegate func(p tview.Primitive)) {
	delegate(m.table)
}

// HasFocus returns whether or not this primitive has focus
func (m *Menu) HasFocus() bool {
	// Check if the active menu has focus
	return m.table.HasFocus()
}

func (m *Menu) InputHandler() func(event *tcell.EventKey, setFocus func(p tview.Primitive)) {
	return m.WrapInputHandler(func(event *tcell.EventKey, setFocus func(p tview.Primitive)) {
		// 将事件传递给表格
		if handler := m.table.InputHandler(); handler != nil {
			handler(event, setFocus)
		}
	})
}

type SortItems []*Item

func (l SortItems) Len() int {
	return len(l)
}

func (l SortItems) Less(i, j int) bool {
	return l[i].Index < l[j].Index
}

func (l SortItems) Swap(i, j int) {
	l[i], l[j] = l[j], l[i]
}