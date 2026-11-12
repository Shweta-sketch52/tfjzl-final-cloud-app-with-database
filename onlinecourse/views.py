
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Course, Enrollment, Question, Choice, Submission
import logging

# Get an instance of a logger
logger = logging.getLogger(__name__)


# User Registration
def registration_request(request):
    context = {}

    if request.method == 'GET':
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context
        )

    elif request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']

        user_exist = False

        try:
            User.objects.get(username=username)
            user_exist = True
        except User.DoesNotExist:
            logger.info("New user registration")

        if not user_exist:
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            login(request, user)
            return redirect("onlinecourse:index")

        else:
            context['message'] = "User already exists."
            return render(
                request,
                'onlinecourse/user_registration_bootstrap.html',
                context
            )


# User Login
def login_request(request):
    context = {}

    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']

        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        else:
            context['message'] = "Invalid username or password."
            return render(
                request,
                'onlinecourse/user_login_bootstrap.html',
                context
            )

    else:
        return render(
            request,
            'onlinecourse/user_login_bootstrap.html',
            context
        )


# User Logout
def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


# Check whether a user is enrolled in a course
def check_if_enrolled(user, course):
    is_enrolled = False

    if user.id is not None:
        num_results = Enrollment.objects.filter(
            user=user,
            course=course
        ).count()

        if num_results > 0:
            is_enrolled = True

    return is_enrolled


# Course List View
class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]

        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)

        return courses


# Course Detail View
class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


# Enroll User in a Course
def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    is_enrolled = check_if_enrolled(user, course)

    if not is_enrolled and user.is_authenticated:
        Enrollment.objects.create(
            user=user,
            course=course,
            mode='honor'
        )

        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(
        reverse(
            viewname='onlinecourse:course_details',
            args=(course.id,)
        )
    )


# Extract selected answers from the exam form
def extract_answers(request):
    submitted_answers = []

    for key in request.POST:
        if key.startswith('choice'):
            try:
                choice_id = int(request.POST[key])
                submitted_answers.append(choice_id)
            except (ValueError, TypeError):
                continue

    return submitted_answers


# Submit Exam
@login_required
def submit(request, course_id):

    # Get the course
    course = get_object_or_404(Course, pk=course_id)

    # Get the enrollment of the logged-in user
    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    # Create a submission record
    submission = Submission.objects.create(
        enrollment=enrollment
    )

    # Collect selected answers
    selected_answers = extract_answers(request)

    # Add selected choices to the submission
    for choice_id in selected_answers:
        choice = get_object_or_404(
            Choice,
            pk=choice_id,
            question__course=course
        )

        submission.choices.add(choice)

    # Redirect to the exam result page
    return redirect(
        'onlinecourse:show_exam_result',
        course_id=course.id,
        submission_id=submission.id
    )


# Display Exam Result
@login_required
def show_exam_result(request, course_id, submission_id):

    # Get the course
    course = get_object_or_404(Course, pk=course_id)

    # Get the submission belonging to the logged-in user
    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__user=request.user,
        enrollment__course=course
    )

    # Get selected choices
    selected_choices = submission.choices.all()

    # Get all questions belonging to the course
    questions = Question.objects.filter(course=course)

    # Calculate total possible marks
    total_marks = sum(
        question.grade for question in questions
    )

    score = 0
    question_results = []

    # Evaluate each question
    for question in questions:

        correct_choices = question.choice_set.filter(
            is_correct=True
        )

        selected_for_question = selected_choices.filter(
            question=question
        )

        correct_ids = set(
            correct_choices.values_list('id', flat=True)
        )

        selected_ids = set(
            selected_for_question.values_list('id', flat=True)
        )

        # Check whether the selected answers are exactly correct
        is_correct = (
            bool(correct_ids) and selected_ids == correct_ids
        )

        if is_correct:
            score += question.grade

        # Store question-wise results
        question_results.append({
            'question': question,
            'selected_choices': selected_for_question,
            'correct_choices': correct_choices,
            'is_correct': is_correct
        })

    # Calculate percentage grade
    if total_marks > 0:
        grade = (score / total_marks) * 100
    else:
        grade = 0

    # Prepare result context
    context = {
        'course': course,
        'submission': submission,
        'grade': grade,
        'score': score,
        'total_marks': total_marks,
        'question_results': question_results
    }

    # Render exam result template
    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context
    )
