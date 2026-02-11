from app.services.llm import get_llm, LLMMessage

llm = get_llm()
print(llm.chat([LLMMessage(role="user", content="Say hello in one sentence.")]))


# running this test script
# cd backend
# python -m scripts.test_llm