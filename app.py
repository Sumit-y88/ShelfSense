"""Streamlit chat interface for the inventory assistant."""

import streamlit as st

from src.pipeline import answer_question


EXAMPLE_QUESTIONS = (
    "Which grocery products are low on stock?",
    "Show me the 5 most recent sales.",
    "List pantry items with their prices.",
    "Which suppliers are in Mumbai?",
)


def _queue_example(question: str) -> None:
    """Save an example question so it can be handled on the next rerun."""
    st.session_state.pending_question = question


def _render_message(message: dict[str, str]) -> None:
    """Display one chat message and its SQL details, if any."""
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message["role"] == "assistant":
            with st.expander("Show SQL"):
                sql = message.get("sql", "")
                if sql:
                    st.code(sql, language="sql")
                else:
                    st.caption("No SQL was generated for this request.")


def main() -> None:
    """Render the chat UI and send submitted questions to the safe pipeline."""
    st.set_page_config(
        page_title="ShelfSense: Supermart Inventory Assistant",
        page_icon="??",
        layout="centered",
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    with st.sidebar:
        st.header("Data access")
        st.markdown("**The AI can access:**")
        st.markdown(
            "- Grocery and household product names, descriptions, prices in INR, and stock levels\n"
            "- Category names\n"
            "- Supplier names and cities\n"
            "- Sales quantities and dates"
        )
        st.markdown("**The AI cannot access:**")
        st.markdown(
            "- Product costs or profit reports\n"
            "- Employee salaries, phone numbers, or HR records"
        )
        st.caption(
            "Inventory questions use a read-only database connection with query checks."
        )

        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pop("pending_question", None)
            st.rerun()

    st.title("ShelfSense: Supermart Inventory Assistant")
    st.write("Ask a question about products, stock, suppliers, or sales.")

    st.subheader("Try an example")
    columns = st.columns(2)
    for index, example in enumerate(EXAMPLE_QUESTIONS):
        with columns[index % 2]:
            st.button(
                example,
                key=f"example_{index}",
                use_container_width=True,
                on_click=_queue_example,
                args=(example,),
            )

    for message in st.session_state.messages:
        _render_message(message)

    typed_question = st.chat_input("Ask an inventory question")
    example_question = st.session_state.pop("pending_question", None)
    question = example_question or typed_question

    if question:
        st.session_state.messages.append({"role": "user", "content": question})

        with st.spinner("Checking the inventory..."):
            result = answer_question(question)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": str(result.get("answer", "I couldn't complete that request.")),
                "sql": str(result.get("sql", "")),
            }
        )
        st.rerun()


if __name__ == "__main__":
    main()
